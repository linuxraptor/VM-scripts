#!/usr/bin/env python3

from __future__ import absolute_import
from __future__ import print_function
from __future__ import division
from __future__ import unicode_literals

import os
import sys
import time
import argparse
import threading
import pycurl
from io import BytesIO

description = 'Download latest Gentoo Stage3 to a given directory.'
# Use what is here to implement retrys.
MIRRORS = ['http://mirror.facebook.net/gentoo/',
           'http://gentoo.mirrors.tds.net/gentoo',
           'ftp://cosmos.illinois.edu/pub/gentoo/',
           'http://cosmos.illinois.edu/pub/gentoo/',
           'http://mirror.csclub.uwaterloo.ca/gentoo-distfiles/',
           'http://mirrors.evowise.com/gentoo/']
RELEASE_DIR = 'releases/amd64/autobuilds/'
CURRENT_VER = "latest-stage3-amd64-hardened.txt"

MIRROR = str(MIRRORS[0] + RELEASE_DIR)

# TODO: Download .DIGESTS, verify checksum with built-in hashlib

class Error(Exception):
  """Base error class."""
  pass


class InputError(Error):
  """Exception raised for errors in the input."""
  pass


class CurlError(Error):
  """Exception raised for curl URL errors."""


def ParseArguments():
  parser = argparse.ArgumentParser(description=description)
  parser.add_argument('--working-dir',
                      default=os.getcwd(),
                      help='Download destination.')
  args = parser.parse_args()
  if not os.path.isdir(args.working_dir):
    raise InputError('No such directory:%s' % args.working_dir)
  return args


class DownloadManager(object):
  """Manages pyCurl."""

  def __init__(self):
    self.download_file = ''
    self.old_total_downloaded = 0
    self.systime = 0

  def FindStage3(self):
    self.url = str(MIRROR + CURRENT_VER)
    self.destination = BytesIO()
    self._Curl()
    response = self.destination.getvalue()
    ascii_response = response.decode()
    stage3_location = ascii_response.splitlines()[-1].split(' ')[0]
    url = (MIRROR + stage3_location)
    return url

  def Download(self, working_dir=os.getcwd()):
    self.url = self.FindStage3()
    self.filename = self.url.split('/')[-1]
    self.download_file = working_dir + '/' + self.filename
    self.destination = 'filehandle'
    self._Curl()
    if self.destination:
      self.destination.close()

  def _Curl(self):
    """Handles the bare pyCurl interface.."""
    def _CurlCleanup():
      if os.path.isfile(self.download_file):
        os.remove(self.download_file)
      self.destination = None

    def _SpawnProgress(total_to_download, total_downloaded, *args, **kwargs):
      current_time = int(time.time())
      if current_time != self.systime:
        self.systime = current_time
        threading.Thread(target=
            _ShowProgress(total_to_download, total_downloaded)).start()

    def _ShowProgress(total_to_download, total_downloaded):
      if total_to_download:
        if self.old_total_downloaded > 0:
          bytes_per_second = (total_downloaded - self.old_total_downloaded)
          speed = _Humanize(bytes_per_second)
        else:
          speed = '0 B/s'
        self.old_total_downloaded = total_downloaded
        percent_completed = float(total_downloaded)/total_to_download
        formatted_percent = format(round((percent_completed * 100),
                                   ndigits=2), '.2f')
        progress = ('%s%%  %s   \r' % (formatted_percent, speed))
        sys.stdout.write(progress)
        sys.stdout.flush()

    def _Humanize(bps):
      mbps = round(((bps / (1024**2)) / 8), ndigits=1)
      if mbps >= 1:
        return (str(mbps) + ' Mb/s')
      kbps = round(((bps / 1024) / 8), ndigits=1)
      if kbps >= 1:
        return (str(kbps) + ' Kb/s')
      bps = round(bps, ndigits=1)
      return (str(bps) + ' B/s')

    if self.destination == 'filehandle':
      download_file = open(self.download_file, 'wb')
    curl_handle = pycurl.Curl()
    curl_handle.setopt(pycurl.FOLLOWLOCATION, 1)
    curl_handle.setopt(pycurl.MAXREDIRS, 5)
    curl_handle.setopt(pycurl.CONNECTTIMEOUT, 60)
    curl_handle.setopt(pycurl.TIMEOUT, 300)
    curl_handle.setopt(pycurl.NOSIGNAL, 1)
    try:
      curl_handle.setopt(pycurl.URL, self.url)
      if self.download_file:
        curl_handle.setopt(pycurl.WRITEDATA, download_file)
        curl_handle.setopt(pycurl.NOPROGRESS, 0)
        curl_handle.setopt(pycurl.PROGRESSFUNCTION, _SpawnProgress)
        print("Downloading %s:" % self.filename)
      else:
        curl_handle.setopt(pycurl.WRITEDATA, self.destination)
      curl_handle.perform()
    except pycurl.error as e:
      _CurlCleanup()
      if e.args[0] == 42:
        print('KeyboardInterrupt')
        _CurlCleanup()
        return
      raise CurlError('Download failed: ', e)
    http_code = curl_handle.getinfo(pycurl.HTTP_CODE)
    # if http_code >= 400
      # try another server. use a retry code.
    if http_code < 200 or http_code >= 300:
      raise CurlError('Received HTTP error code: ', http_code)
      _CurlCleanup()
  
    curl_handle.close()
    return self.destination


if __name__ == "__main__":
  arguments = ParseArguments()
  download_manager = DownloadManager()
  download_manager.Download(arguments.working_dir)

