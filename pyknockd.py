#!/usr/bin/env python

import socket
import sys
import os
import hashlib
import hmac
import string
import argparse
import struct
import time


DIGEST = hashlib.sha256
DIGEST_SIZE = DIGEST().digest_size

HDR_FMT = "<%dsBdi" % (DIGEST_SIZE,)
HDR_SIZE = struct.calcsize(HDR_FMT)

CODE_OPEN = 1
CODE_CLOSE = 2


def compare_digest_polyfill(a, b):
    if len(a) != len(b):
        return False

    result = 0
    for x, y in zip(a, b):
        result |= ord(x) ^ ord(y)
    return result == 0


if sys.hexversion >= 0x020707F0:
    compare_digest = hmac.compare_digest
else:
    compare_digest = compare_digest_polyfill


def detect_af(addr):
    return socket.getaddrinfo(addr,
                              None,
                              socket.AF_UNSPEC,
                              0,
                              0,
                              socket.AI_NUMERICHOST)[0][0]


def check_port(value):
    ivalue = int(value)
    if not (0 < ivalue < 65536):
        raise argparse.ArgumentTypeError(
            "%s is not a valid port number" % value)
    return ivalue


def psk(value):
    if (sys.version_info > (3, 0)):
        return bytes(value, 'latin-1')
    else:
        return value


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-b",
                        "--bind-address",
                        help="bind address",
                        default="")
    parser.add_argument("-p",
                        "--port",
                        help="bind port",
                        type=check_port, default=60120,
                        metavar="PORT")
    parser.add_argument("-t",
                        "--time-drift",
                        help="allowed time drift in seconds"
                        " between client and server. "
                        "Value may be a floating point number",
                        type=float,
                        default=60,
                        metavar="DRIFT")
    parser.add_argument("psk",
                        help="pre-shared key used to authenticate clients",
                        type=psk,
                        metavar="PSK")
    parser.add_argument("open_cmd",
                        help="template of command used to enable access. "
                        "Example: \"ipset add -exist myset $ip\". "
                        "Available variables: $ip, $af, $cmd",
                        metavar="OPEN_CMD")
    parser.add_argument("close_cmd",
                        help="template of command used to disable access. "
                        "Example: \"ipset del -exist myset $ip\". "
                        "Available variables: $ip, $af, $cmd",
                        metavar="CLOSE_CMD")
    return parser.parse_args()


af_map = {
    socket.AF_INET: "inet",
    socket.AF_INET6: "inet6"
}


def main():
    args = parse_args()

    if args.bind_address:
        bf = detect_af(args.bind_address)
        s = socket.socket(bf, socket.SOCK_DGRAM)
    else:
        s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
    s.bind((args.bind_address, args.port))

    open_cmd = string.Template(args.open_cmd)
    close_cmd = string.Template(args.close_cmd)

    try:
        while True:
            data = s.recvfrom(4096)[0]
            if not data:
                continue

            digest, opcode, ts, af = struct.unpack(HDR_FMT, data[:HDR_SIZE])
            binaddr = data[HDR_SIZE:]

            if abs(ts - time.time()) > args.time_drift:
                continue

            if not compare_digest(hmac.new(args.psk,
                                           data[DIGEST_SIZE:],
                                           DIGEST).digest(),
                                  digest):
                continue

            str_af = af_map.get(af, str(af))
            str_addr = socket.inet_ntop(af, binaddr)
            if opcode == CODE_OPEN:
                os.system(open_cmd.safe_substitute(ip=str_addr,
                                                   af=str_af,
                                                   cmd="open"))
            elif opcode == CODE_CLOSE:
                os.system(close_cmd.safe_substitute(ip=str_addr,
                                                    af=str_af,
                                                    cmd="close"))
    except Exception as e:
        sys.stderr.write("Unhandled Exception: %s" % (str(e),) + os.linesep)


if __name__ == '__main__':
    main()
