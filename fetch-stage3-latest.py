#!/usr/bin/python3

from __future__ import absolute_import
from __future__ import print_function
from __future__ import division
from __future__ import unicode_literals

import os
import sys
import time
import argparse
import pycurl
from io import BytesIO

description = 'Download latest Gentoo Stage3 to a given directory.'
# MIRROR = ("http://mirror.facebook.net/"
#           "gentoo/releases/amd64/autobuilds/")
# Use what is here to implement retrys.
MIRRORS = ['http://mirror.facebook.net/gentoo/',
           'http://gentoo.mirrors.tds.net/gentoo',
           'ftp://cosmos.illinois.edu/pub/gentoo/',
           'http://cosmos.illinois.edu/pub/gentoo/',
           'http://mirror.csclub.uwaterloo.ca/gentoo-distfiles/',
           'http://mirrors.evowise.com/gentoo/']
RELEASE_DIR = 'releases/amd64/autobuilds/'
CURRENT_VER = "latest-stage3-amd64-hardened.txt"

MIRROR = str(MIRRORS[2] + RELEASE_DIR)

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

  def FindStage3(self):
    self.url = str(MIRROR + CURRENT_VER)
    self.destination = BytesIO()
    self._Curl()
    response = self.destination.getvalue()
    ascii_response = response.decode()
    for line in ascii_response.splitlines():
      if '#' not in line:
        stage3_location = line.split(' ')[0]
    url = (MIRROR + stage3_location)
    return url

  def Download(self, working_dir=os.getcwd()):
    self.url = self.FindStage3()
    self.filename = self.url.split('/')[-1]
    self.download_file = working_dir + '/' + self.filename
    self.destination = open(self.download_file, 'wb')
    self._Curl()
    if self.destination:
      self.destination.close()

  def _Curl(self):
    """Handles the bare pyCurl interface.."""
    def _CurlCleanup():
      if os.path.isfile(self.download_file):
        os.remove(self.download_file)
      self.destination = None

    def _ShowProgress(total_to_download, total_downloaded, *args, **kwargs):
      if total_to_download:
        time.sleep(0.5)
        percent_completed = float(total_downloaded)/total_to_download
        rate = round(percent_completed * 100, ndigits=2)
        sys.stdout.write('%s%%\r' % rate)
        sys.stdout.flush()

    curl_handle = pycurl.Curl()
    curl_handle.setopt(pycurl.FOLLOWLOCATION, 1)
    curl_handle.setopt(pycurl.MAXREDIRS, 5)
    curl_handle.setopt(pycurl.CONNECTTIMEOUT, 60)
    curl_handle.setopt(pycurl.TIMEOUT, 300)
    curl_handle.setopt(pycurl.NOSIGNAL, 1)
    try:
      curl_handle.setopt(pycurl.WRITEDATA, self.destination)
      curl_handle.setopt(pycurl.URL, self.url)
      if self.download_file:
        curl_handle.setopt(pycurl.NOPROGRESS, 0)
        curl_handle.setopt(pycurl.PROGRESSFUNCTION, _ShowProgress)
        print("Downloading %s:" % self.filename)
      curl_handle.perform()
    except pycurl.error as e:
      _CurlCleanup()
      if e.args[0] == 42:
        print('KeyboardInterrupt')
        _CurlCleanup()
        return
      raise CurlError('Download failed: ', e)
    http_code = curl_handle.getinfo(pycurl.HTTP_CODE)
    if http_code < 200 or http_code >= 300:
      raise CurlError('Received HTTP error code: ', http_code)
      _CurlCleanup()
  
    curl_handle.close()
    return self.destination


if __name__ == "__main__":
  arguments = ParseArguments()
  download_manager = DownloadManager()
  download_manager.Download(arguments.working_dir)

