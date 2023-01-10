from ping_func import multi_ping_query



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

