
"""
#!/usr/bin/env python3

    Other Repositories of python-ping
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    * https://github.com/l4m3rx/python-ping      supports Python2 and Python3
    * https://bitbucket.org/delroth/python-ping
    About
    ~~~~~
    A pure python ping implementation using raw socket.
    Note that ICMP messages can only be sent from processes running as root.
    Derived from ping.c distributed in Linux's netkit. That code is
    copyright (c) 1989 by The Regents of the University of California.
    That code is in turn derived from code written by Mike Muuss of the
    US Army Ballistic Research Laboratory in December, 1983 and
    placed in the public domain. They have my thanks.
    Bugs are naturally mine. I'd be glad to hear about them. There are
    certainly word - size dependenceies here.
    Copyright (c) Matthew Dixon Cowles, <http://www.visi.com/~mdc/>.
    Distributable under the terms of the GNU General Public License
    version 2. Provided with no warranties of any sort.
    Original Version from Matthew Dixon Cowles:
      -> ftp://ftp.visi.com/users/mdc/ping.py
    Rewrite by Jens Diemer:
      -> http://www.python-forum.de/post-69122.html#69122
    Rewrite by Johannes Meyer:
      -> http://www.python-forum.de/viewtopic.php?p=183720
    Revision history
    ~~~~~~~~~~~~~~~~
    November 1, 2010
    Rewrite by Johannes Meyer:
     -  changed entire code layout
     -  changed some comments and docstrings
     -  replaced time.clock() with time.time() in order
        to be able to use this module on linux, too.
     -  added global __all__, ICMP_CODE and ERROR_DESCR
     -  merged functions "do_one" and "send_one_ping"
     -  placed icmp packet creation in its own function
     -  removed timestamp from the icmp packet
     -  added function "multi_ping_query"
     -  added class "PingQuery"
    May 30, 2007
    little rewrite by Jens Diemer:
     -  change socket asterisk import to a normal import
     -  replace time.time() with time.clock()
     -  delete "return None" (or change to "return" only)
     -  in checksum() rename "str" to "source_string"
    November 22, 1997
    Initial hack. Doesn't do much, but rather than try to guess
    what features I (or others) will want in the future, I've only
    put in what I need now.
    December 16, 1997
    For some reason, the checksum bytes are in the wrong order when
    this is run under Solaris 2.X for SPARC but it works right under
    Linux x86. Since I don't know just what's wrong, I'll swap the
    bytes always and then do an htons().
    December 4, 2000
    Changed the struct.pack() calls to pack the checksum and ID as
    unsigned. My thanks to Jerome Poincheval for the fix.
"""

import os
import csv
import time
import socket
import struct
import select
import random
import datetime

# asyncore was removed in Python 3.12. It is only needed by the (optional)
# PingQuery / multi_ping_query helpers, so import it lazily and keep the rest
# of the module usable when it is unavailable.
try:
    import asyncore
except ImportError:
    asyncore = None

# added by swgu
import numpy

# From /usr/include/linux/icmp.h; your milage may vary.
ICMP_ECHO_REQUEST = 8 # Seems to be the same on Solaris.
ICMP_ECHO_REPLY = 0

# ICMP header: type(1) code(1) checksum(2) id(2) sequence(2) = 8 bytes.
ICMP_HEADER_FORMAT = 'bbHHH'
ICMP_HEADER_SIZE = struct.calcsize(ICMP_HEADER_FORMAT)  # 8
# The payload starts with a high-resolution send timestamp (time.perf_counter,
# a C double). The reply echoes the payload back unchanged, so the round-trip
# time is derived from the reply itself and is immune to mismatched replies.
ICMP_TIMESTAMP_FORMAT = 'd'
ICMP_TIMESTAMP_SIZE = struct.calcsize(ICMP_TIMESTAMP_FORMAT)  # 8
ICMP_PAYLOAD_SIZE = 192  # historical data-field size

ICMP_CODE = socket.getprotobyname('icmp')
ERROR_DESCR = {
    1: ' - Note that ICMP messages can only be '
       'sent from processes running as root.',
    10013: ' - Note that ICMP messages can only be sent by'
           ' users or processes with administrator rights.'
    }

__all__ = ['create_packet', 'do_one', 'verbose_ping', 'PingQuery',
           'multi_ping_query']


def checksum(source_string):
    # I'm not too confident that this is right but testing seems to
    # suggest that it gives the same answers as in_cksum in ping.c.
    sum = 0
    count_to = (len(source_string) // 2) * 2
    count = 0
    while count < count_to:
        # source_string is a bytes object, so indexing already yields ints.
        this_val = source_string[count + 1] * 256 + source_string[count]
        sum = sum + this_val
        sum = sum & 0xffffffff # Necessary?
        count = count + 2
    if count_to < len(source_string):
        sum = sum + source_string[len(source_string) - 1]
        sum = sum & 0xffffffff # Necessary?
    sum = (sum >> 16) + (sum & 0xffff)
    sum = sum + (sum >> 16)
    answer = ~sum
    answer = answer & 0xffff
    # Swap bytes. Bugger me if I know why.
    answer = answer >> 8 | (answer << 8 & 0xff00)
    return answer


def create_packet(packet_id, sequence=1, timestamp=None):
    """Create an ICMP echo request packet.

    "packet_id" and "sequence" identify the request so its reply can be told
    apart from other traffic. "timestamp" (a time.perf_counter reading, in
    seconds) is embedded at the start of the payload so the receiver can
    compute the round-trip time from the reply; it defaults to "now".
    """
    if timestamp is None:
        timestamp = time.perf_counter()
    # Header is type (8), code (8), checksum (16), id (16), sequence (16)
    header = struct.pack(ICMP_HEADER_FORMAT, ICMP_ECHO_REQUEST, 0, 0,
                         packet_id, sequence)
    payload = struct.pack(ICMP_TIMESTAMP_FORMAT, timestamp)
    payload += (ICMP_PAYLOAD_SIZE - len(payload)) * b'Q'
    # Calculate the checksum on the data and the dummy header.
    my_checksum = checksum(header + payload)
    # Now that we have the right checksum, we put that in. It's just easier
    # to make up a new header than to stuff it into the dummy.
    header = struct.pack(ICMP_HEADER_FORMAT, ICMP_ECHO_REQUEST, 0,
                         socket.htons(my_checksum), packet_id, sequence)
    return header + payload


def new_icmp_socket():
    """
    Return a tuple "(socket, is_raw)" for sending ICMP echo requests.

    Prefers an unprivileged datagram socket (SOCK_DGRAM), which needs no root
    as long as the caller's gid is within /proc/sys/net/ipv4/ping_group_range.
    Falls back to a raw socket (SOCK_RAW), which requires root.
    "is_raw" tells the receiver how to parse replies (see "receive_ping").
    """
    try:
        return socket.socket(socket.AF_INET, socket.SOCK_DGRAM, ICMP_CODE), False
    except socket.error:
        # Unprivileged ICMP not available; fall back to a raw socket.
        my_socket = socket.socket(socket.AF_INET, socket.SOCK_RAW, ICMP_CODE)
        return my_socket, True


def ping_once(my_socket, is_raw, dest_ip, packet_id, sequence, timeout):
    """
    Send one echo request on the already-open "my_socket" and wait for its
    matching reply. Returns the round-trip time in seconds, or None on timeout.
    """
    # Stamp the send time as late as possible, then build+send immediately.
    send_time = time.perf_counter()
    packet = create_packet(packet_id, sequence, send_time)
    try:
        while packet:
            # The icmp protocol does not use a port, but sendto expects one,
            # so we just give it a dummy port.
            sent = my_socket.sendto(packet, (dest_ip, 1))
            packet = packet[sent:]
    except socket.error:
        return None
    return receive_ping(my_socket, is_raw, packet_id, sequence, timeout)


def receive_ping(my_socket, is_raw, packet_id, sequence, timeout):
    """
    Wait up to "timeout" seconds for the echo reply matching this request and
    return its round-trip time in seconds, or None on timeout.

    Matching is strict: the reply must be an echo reply carrying the expected
    sequence number (and, for a raw socket, the expected id). A raw socket
    delivers the full IP packet, so the ICMP header starts at byte 20 and every
    icmp reply on the host is seen (hence the id check). A datagram socket
    delivers just the ICMP message (offset 0) and the kernel routes only our
    replies to us, but it rewrites the id, so we rely on the sequence number.

    The round-trip time is computed from the send timestamp echoed back in the
    payload, so a delayed, duplicated or foreign reply can never corrupt a
    measurement.
    """
    offset = 20 if is_raw else 0
    ts_start = offset + ICMP_HEADER_SIZE
    time_left = timeout
    while time_left > 0:
        started = time.perf_counter()
        ready = select.select([my_socket], [], [], time_left)
        if not ready[0]:  # timeout
            return None
        recv_time = time.perf_counter()
        try:
            rec_packet, addr = my_socket.recvfrom(1024)
        except socket.error:
            time_left -= time.perf_counter() - started
            continue
        time_left -= time.perf_counter() - started
        if len(rec_packet) < ts_start + ICMP_TIMESTAMP_SIZE:
            continue  # too short to be one of our replies
        r_type, r_code, r_cksum, r_id, r_seq = struct.unpack(
            ICMP_HEADER_FORMAT, rec_packet[offset:offset + ICMP_HEADER_SIZE])
        if r_type != ICMP_ECHO_REPLY or r_seq != sequence:
            continue  # not the reply we are waiting for
        if is_raw and r_id != packet_id:
            continue  # some other ping running on this host
        (sent_time,) = struct.unpack(
            ICMP_TIMESTAMP_FORMAT,
            rec_packet[ts_start:ts_start + ICMP_TIMESTAMP_SIZE])
        return recv_time - sent_time
    return None


def do_one(dest_addr, timeout=1):
    """
    Sends one ping to the given "dest_addr" which can be an ip or hostname.
    "timeout" can be any integer or float except negatives and zero.
    Returns either the delay (in seconds) or None on timeout and an invalid
    address, respectively.
    """
    try:
        my_socket, is_raw = new_icmp_socket()
    except socket.error as e:
        if e.errno in ERROR_DESCR:
            # Operation not permitted
            raise socket.error(''.join((e.args[1], ERROR_DESCR[e.errno])))
        raise # raise the original error
    try:
        dest_ip = socket.gethostbyname(dest_addr)
    except socket.gaierror:
        my_socket.close()
        return None
    # The id fits an unsigned short and identifies our replies on a raw socket.
    packet_id = os.getpid() & 0xFFFF
    try:
        return ping_once(my_socket, is_raw, dest_ip, packet_id, 1, timeout)
    finally:
        my_socket.close()


def verbose_ping(dest_addr, timeout=2, count=100, interval=0):
    """
    Pings "dest_addr" (ip or hostname) "count" times over a single reused
    socket and prints summary statistics (in milliseconds) of the successful
    replies. Also writes a per-ping CSV log to "ping<count>.csv" with columns
    "seq,timestamp,rtt_ms" (rtt_ms is left blank on timeout), so the run can be
    analysed as a time series.

    "timeout"  per-ping wait, in seconds.
    "count"    number of echo requests to send.
    "interval" optional pause between successive pings, in seconds
               (0 = back-to-back).
    """
    delay_array = []   # per-ping round-trip times in milliseconds (added by swgu)
    rows = []          # (seq, iso_timestamp, rtt_ms_or_None) for the CSV log

    try:
        my_socket, is_raw = new_icmp_socket()
    except socket.error as e:
        if e.errno in ERROR_DESCR:
            # Operation not permitted
            raise socket.error(''.join((e.args[1], ERROR_DESCR[e.errno])))
        raise # raise the original error
    try:
        dest_ip = socket.gethostbyname(dest_addr)
    except socket.gaierror:
        my_socket.close()
        print('failed. (cannot resolve {})'.format(dest_addr))
        return

    # One id for the whole run; the sequence number identifies each request.
    packet_id = os.getpid() & 0xFFFF
    try:
        for sequence in range(count):
            # Wall-clock send time for the time-series log (RTT itself is still
            # measured with the monotonic clock inside ping_once).
            sent_at = datetime.datetime.now().isoformat(timespec='microseconds')
            delay = ping_once(my_socket, is_raw, dest_ip, packet_id,
                              sequence & 0xFFFF, timeout)
            if delay is None:
                print('failed. (Timeout within {} seconds.)'.format(timeout))
                rows.append((sequence, sent_at, None))
            else:
                rtt_ms = round(delay * 1000.0, 4)
                delay_array.append(rtt_ms)
                rows.append((sequence, sent_at, rtt_ms))
            if interval:
                time.sleep(interval)
    finally:
        my_socket.close()

    if delay_array:
        print('mean: ', numpy.mean(delay_array))
        print('var: ', numpy.var(delay_array))
        print('std: ', numpy.std(delay_array))
        print('min: ', numpy.min(delay_array))
        print('max: ', numpy.max(delay_array))
    else:
        print('No responses received; no statistics to report.')

    filename = 'ping' + str(count) + '.csv'
    print('filename: ', filename)
    with open(filename, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['seq', 'timestamp', 'rtt_ms'])
        for seq, ts, rtt_ms in rows:
            writer.writerow([seq, ts, '' if rtt_ms is None else rtt_ms])

    print('')


if asyncore is not None:
    _Dispatcher = asyncore.dispatcher
else:
    class _Dispatcher(object):
        # Fallback so the module still imports on Python 3.12+ where asyncore
        # was removed. Using PingQuery/multi_ping_query then fails loudly.
        def __init__(self, *args, **kwargs):
            raise RuntimeError(
                "PingQuery/multi_ping_query require the 'asyncore' module, "
                "which was removed in Python 3.12. Use verbose_ping() or "
                "do_one() instead.")


class PingQuery(_Dispatcher):
    def __init__(self, host, p_id, timeout=0.5, ignore_errors=False):
        """
       Derived class from "asyncore.dispatcher" for sending and
       receiving an icmp echo request/reply.
       
       Usually this class is used in conjunction with the "loop"
       function of asyncore.
       
       Once the loop is over, you can retrieve the results with
       the "get_result" method. Assignment is possible through
       the "get_host" method.
       
       "host" represents the address under which the server can be reached.
       "timeout" is the interval which the host gets granted for its reply.
       "p_id" must be any unique integer or float except negatives and zeros.
       
       If "ignore_errors" is True, the default behaviour of asyncore
       will be overwritten with a function which does just nothing.
       
       """
        _Dispatcher.__init__(self)
        try:
            self.create_socket(socket.AF_INET, socket.SOCK_RAW, ICMP_CODE)
        except socket.error as e:
            if e.errno in ERROR_DESCR:
                # Operation not permitted
                raise socket.error(''.join((e.args[1], ERROR_DESCR[e.errno])))
            raise # raise the original error
        self.time_received = 0
        self.time_sent = 0
        self.timeout = timeout
        # Maximum for an unsigned short int c object counts to 65535 so
        # we have to sure that our packet id is not greater than that.
        self.packet_id = int((id(timeout) / p_id) % 65535)
        self.host = host
        self.packet = create_packet(self.packet_id)
        if ignore_errors:
            # If it does not care whether an error occured or not.
            self.handle_error = self.do_not_handle_errors
            self.handle_expt = self.do_not_handle_errors

    def writable(self):
        return self.time_sent == 0

    def handle_write(self):
        self.time_sent = time.time()
        while self.packet:
            # The icmp protocol does not use a port, but the function
            # below expects it, so we just give it a dummy port.
            sent = self.sendto(self.packet, (self.host, 1))
            self.packet = self.packet[sent:]

    def readable(self):
        # As long as we did not sent anything, the channel has to be left open.
        if (not self.writable()
            # Once we sent something, we should periodically check if the reply
            # timed out.
            and self.timeout < (time.time() - self.time_sent)):
            self.close()
            return False
        # If the channel should not be closed, we do not want to read something
        # until we did not sent anything.
        return not self.writable()

    def handle_read(self):
        read_time = time.time()
        packet, addr = self.recvfrom(1024)
        header = packet[20:28]
        type, code, checksum, p_id, sequence = struct.unpack("bbHHh", header)
        if p_id == self.packet_id:
            # This comparison is necessary because winsocks do not only get
            # the replies for their own sent packets.
            self.time_received = read_time
            self.close()

    def get_result(self):
        """Return the ping delay if possible, otherwise None."""
        if self.time_received > 0:
            return self.time_received - self.time_sent

    def get_host(self):
        """Return the host where to the request has or should been sent."""
        return self.host

    def do_not_handle_errors(self):
        # Just a dummy handler to stop traceback printing, if desired.
        pass

    def create_socket(self, family, type, proto):
        # Overwritten, because the original does not support the "proto" arg.
        sock = socket.socket(family, type, proto)
        sock.setblocking(0)
        self.set_socket(sock)
        # Part of the original but is not used. (at least at python 2.7)
        # Copied for possible compatiblity reasons.
        self.family_and_type = family, type

    # If the following methods would not be there, we would see some very
    # "useful" warnings from asyncore, maybe. But we do not want to, or do we?
    def handle_connect(self):
        pass

    def handle_accept(self):
        pass

    def handle_close(self):
        self.close()


def multi_ping_query(hosts, timeout=1, step=512, ignore_errors=False):
    """
    Sends multiple icmp echo requests at once.
    "hosts" is a list of ips or hostnames which should be pinged.
    "timeout" must be given and a integer or float greater than zero.
    "step" is the amount of sockets which should be watched at once.
    See the docstring of "PingQuery" for the meaning of "ignore_erros".
    """
    results, host_list, id = {}, [], 0
    for host in hosts:
        try:
            host_list.append(socket.gethostbyname(host))
        except socket.gaierror:
            results[host] = None
    while host_list:
        sock_list = []
        for ip in host_list[:step]: # select supports only a max of 512
            id += 1
            sock_list.append(PingQuery(ip, id, timeout, ignore_errors))
            host_list.remove(ip)
        # Remember to use a timeout here. The risk to get an infinite loop
        # is high, because noone can guarantee that each host will reply!
        asyncore.loop(timeout)
        for sock in sock_list:
            results[sock.get_host()] = sock.get_result()
    return results


if __name__ == '__main__':
    # Testing
#    verbose_ping('www.heise.de')
#    verbose_ping('google.com')
#    verbose_ping('an-invalid-test-url.com')
#    verbose_ping('127.0.0.1')
#    host_list = ['www.heise.de', 'google.com', '127.0.0.1', 'an-invalid-test-url.com']
    dest_addr = input("Please input the IP address (or hostname) to ping : ").strip()
    timeout = int(input("Please input timeout to wait for ping response (unit: ms) : "))
    count = int(input("Please input the number of count to ping : "))
    interval = int(input("Please input interval between pings (unit: ms, 0 = back-to-back, 1000 = like system ping) : "))

    # verbose_ping expects seconds, but the prompts ask for milliseconds.
    verbose_ping(dest_addr, timeout / 1000.0, count, interval / 1000.0)
    # verbose_ping('34.159.134.245', timeout, count)
    
    
    # host_list = ['34.159.104.220', '34.159.134.245']
    # for host, ping in multi_ping_query(host_list).iteritems():
    #     print(host, '=', ping)

