#!/usr/bin/env python3

"""
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

import time
import socket
import struct
import select
import random

# From /usr/include/linux/icmp.h; your milage may vary.
ICMP_ECHO_REQUEST = 8 # Seems to be the same on Solaris.
ICMP_ECHO_REPLY = 0

ICMP_CODE = socket.getprotobyname('icmp')
ERROR_DESCR = {
    1: ' - Note that ICMP messages can only be '
       'sent from processes running as root.',
    10013: ' - Note that ICMP messages can only be sent by'
           ' users or processes with administrator rights.'
    }

__all__ = ['create_packet', 'do_one', 'verbose_ping', 'multi_ping_query']


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


def create_packet(id):
    """Create a new echo request packet based on the given "id"."""
    # Header is type (8), code (8), checksum (16), id (16), sequence (16)
    header = struct.pack('bbHHh', ICMP_ECHO_REQUEST, 0, 0, id, 1)
    data = 192 * b'Q'
    # Calculate the checksum on the data and the dummy header.
    my_checksum = checksum(header + data)
    # Now that we have the right checksum, we put that in. It's just easier
    # to make up a new header than to stuff it into the dummy.
    header = struct.pack('bbHHh', ICMP_ECHO_REQUEST, 0,
                         socket.htons(my_checksum), id, 1)
    return header + data


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
        host = socket.gethostbyname(dest_addr)
    except socket.gaierror:
        my_socket.close()
        return
    # Maximum for an unsigned short int c object counts to 65535 so
    # we have to sure that our packet id is not greater than that.
    packet_id = int((id(timeout) * random.random()) % 65535)
    packet = create_packet(packet_id)
    while packet:
        # The icmp protocol does not use a port, but the function
        # below expects it, so we just give it a dummy port.
        sent = my_socket.sendto(packet, (host, 1))
        packet = packet[sent:]
    delay = receive_ping(my_socket, packet_id, time.time(), timeout, is_raw)
    my_socket.close()
    return delay


def receive_ping(my_socket, packet_id, time_sent, timeout, is_raw=True):
    # Receive the ping from the socket.
    # A raw socket delivers the full IP packet, so the ICMP header starts at
    # byte 20 and every icmp reply on the host is delivered (hence we match on
    # packet_id). A datagram socket delivers just the ICMP message (offset 0)
    # and the kernel already routed only our reply to us, so any echo reply is
    # ours (the kernel also rewrites the id, so matching on it is unreliable).
    offset = 20 if is_raw else 0
    time_left = timeout
    while True:
        started_select = time.time()
        ready = select.select([my_socket], [], [], time_left)
        how_long_in_select = time.time() - started_select
        if ready[0] == []: # Timeout
            return
        time_received = time.time()
        rec_packet, addr = my_socket.recvfrom(1024)
        icmp_header = rec_packet[offset:offset + 8]
        type, code, checksum, p_id, sequence = struct.unpack(
            'bbHHh', icmp_header)
        if (p_id == packet_id) if is_raw else (type == ICMP_ECHO_REPLY):
            return time_received - time_sent
        time_left -= time_received - time_sent
        if time_left <= 0:
            return


def verbose_ping(dest_addr, timeout=2, count=4):
    """
    Sends one ping to the given "dest_addr" which can be an ip or hostname.
    "timeout" can be any integer or float except negatives and zero.
    "count" specifies how many pings will be sent.
    Displays the result on the screen.
 
    """
    for i in range(count):
        print('ping {}...'.format(dest_addr))
        delay = do_one(dest_addr, timeout)
        if delay == None:
            print('failed. (Timeout within {} seconds.)'.format(timeout))
        else:
            delay = round(delay * 1000.0, 4)
            print('get ping in {} milliseconds.'.format(delay))
    print('')


def multi_ping_query(hosts, timeout=1, step=512, ignore_errors=False):
    """
    Sends multiple icmp echo requests at once and collects the replies.

    "hosts" is a list of ips or hostnames which should be pinged.
    "timeout" is the number of seconds to wait for the replies.
    "step" limits how many sockets are watched by select at once
    (select supports only a maximum of 512).
    If "ignore_errors" is True, hosts that cannot be pinged (e.g. because
    raw sockets are not permitted) are reported as None instead of raising.

    Returns a dict mapping each host to its round-trip delay in seconds,
    or None on timeout / unresolvable address.

    This is a "select"-based rewrite of the original "asyncore" version,
    since the asyncore module was removed in Python 3.12.
    """
    results = {}
    queue = []          # (host, ip, packet_id) still to be pinged
    packet_id = 0
    for host in hosts:
        try:
            ip = socket.gethostbyname(host)
        except socket.gaierror:
            results[host] = None
            continue
        # Keep the packet id within an unsigned short (max 65535).
        packet_id = (packet_id + 1) % 65535
        queue.append((host, ip, packet_id))
        results[host] = None

    # Watch at most "step" sockets per select() call.
    for start in range(0, len(queue), step):
        batch = queue[start:start + step]
        id_to_host = {}     # packet_id -> host (used for raw sockets)
        sock_to_host = {}   # socket -> host (used for datagram sockets)
        time_sent = {}      # host -> send timestamp
        socks = []
        is_raw = True       # default until a socket is actually created
        for host, ip, p_id in batch:
            try:
                sock, is_raw = new_icmp_socket()
            except socket.error as e:
                if ignore_errors:
                    continue
                if e.errno in ERROR_DESCR:
                    # Operation not permitted
                    raise socket.error(''.join((e.args[1],
                                                ERROR_DESCR[e.errno])))
                raise # raise the original error
            sock.setblocking(False)
            id_to_host[p_id] = host
            sock_to_host[sock] = host
            time_sent[host] = time.time()
            socks.append(sock)
            # The icmp protocol does not use a port, but sendto expects one,
            # so we just give it a dummy port.
            sock.sendto(create_packet(p_id), (ip, 1))

        # See "receive_ping" for why raw and datagram sockets are matched
        # differently.
        offset = 20 if is_raw else 0
        remaining = len(sock_to_host)
        end_time = time.time() + timeout
        while remaining > 0:
            time_left = end_time - time.time()
            if time_left <= 0:
                break
            ready, _, _ = select.select(socks, [], [], time_left)
            if not ready:
                break # timed out
            recv_time = time.time()
            for sock in ready:
                try:
                    rec_packet, addr = sock.recvfrom(1024)
                except socket.error:
                    continue
                type_, code, chk, r_id, seq = struct.unpack(
                    'bbHHh', rec_packet[offset:offset + 8])
                if is_raw:
                    # A raw socket receives every icmp reply on the host, so
                    # we match replies to their request by packet id.
                    host = id_to_host.get(r_id)
                else:
                    # The kernel already delivered only our reply to this
                    # datagram socket, so any echo reply on it is ours.
                    host = sock_to_host.get(sock)
                    if type_ != ICMP_ECHO_REPLY:
                        host = None
                if host is not None and results[host] is None:
                    results[host] = recv_time - time_sent[host]
                    remaining -= 1
        for sock in socks:
            sock.close()
    return results


"""
if __name__ == '__main__':
    # Testing
#    verbose_ping('www.heise.de')
#    verbose_ping('google.com')
#    verbose_ping('an-invalid-test-url.com')
#    verbose_ping('127.0.0.1')
#    host_list = ['www.heise.de', 'google.com', '127.0.0.1', 'an-invalid-test-url.com']

    host_list = ['google.com']
    for host, ping in multi_ping_query(host_list).iteritems():
        print(host, '=', ping)
"""        
