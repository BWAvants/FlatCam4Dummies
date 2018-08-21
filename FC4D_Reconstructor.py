import logging
import socket
from select import select
import numpy as np
from time import time


if __name__ == '__main__':
    import sys
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('-l', '--log_level', help='Specify log verbosity')

    args = parser.parse_args()
    if args.log_level:
        if 'critical' in args.log_level:
            logging.basicConfig(level=logging.CRITICAL)
        elif 'error' in args.log_level:
            logging.basicConfig(level=logging.ERROR)
        elif 'warning' in args.log_level:
            logging.basicConfig(level=logging.WARNING)
        elif 'info' in args.log_level:
            logging.basicConfig(level=logging.INFO)
        elif 'debug' in args.log_level:
            logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.connect(('127.0.0.1', 0xFC4D))
    except socket.timeout:
        logging.critical('Cannot connect to CameraGrabber')
        sys.exit(1)

    connected = True
    stream = []

    sock.send(b'framedonotify\n')
    while connected and len(stream) == 0:
        r, w, e = select([sock, ], [], [], 0.01)
        for c in r:
            try:
                data = c.recv(1024)
            except ConnectionResetError as e:
                logging.debug(e)
                connected = False
                try:
                    c.shutdown(socket.SHUT_RDWR)
                except OSError as e:
                    logging.debug(e)
                finally:
                    c.close()
                    logging.info('CameraGrabber Connection Lost - Shutting down')
                    sys.exit(0)
            if len(data) == 0:
                try:
                    c.shutdown(socket.SHUT_RDWR)
                except OSError as e:
                    logging.debug(e)
                finally:
                    c.close()
                    logging.info('CameraGrabber Connection Lost - Shutting down')
                    sys.exit(0)
            stream += data.decode('utf-8')

    while connected:
        pass

    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError as e:
        logging.debug(e)
    finally:
        sock.close()