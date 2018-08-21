import logging
import socket
from select import select
import numpy as np
from time import time

global connected, MMFile


def shutdown():
    global connected, MMFile
    connected = False
    if MMFile is not None:
        del MMFile


def check_socket(s: socket):
    packet = b''
    r, _w, _e = select([s, ], [], [], 0.01)
    for c in r:
        try:
            packet = c.recv(1024)
        except ConnectionResetError as e:
            logging.debug(e)
            try:
                c.shutdown(socket.SHUT_RDWR)
            except OSError as e:
                logging.debug(e)
            finally:
                c.close()
                logging.info('CameraGrabber Connection Lost - Shutting down')
                shutdown()
        else:
            if len(packet) == 0:
                try:
                    c.shutdown(socket.SHUT_RDWR)
                except OSError as e:
                    logging.debug(e)
                finally:
                    c.close()
                    logging.info('CameraGrabber Connection Lost - Shutting down')
                    shutdown()
    return packet


def process_image():
    global MMFile
    pass


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
        sys.exit(0)

    connected = True
    MMFile = None
    stream = []

    sock.send(b'framedonotify\n')
    while connected:
        stream += check_socket(sock).decode('utf-8')
        try:
            message, stream = stream.split('\n', 1)
        except ValueError:
            continue
        except Exception as e:
            logging.error(e)
            shutdown()
        else:
            if 'ActiveFile' in message:
                parts = message.split(':')
                if MMFile is not None:
                    del MMFile
                MMFile = np.memmap(parts[1], mode='r', shape=(parts[2], parts[3]), dtype=parts[4])
            elif 'cap' in message:
                process_image()

    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError as e:
        logging.debug(e)
    finally:
        try:
            sock.send(b'framenonotify\n')
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            logging.debug('Could not unregister and/or shutdown communication cleanly')
        sock.close()

