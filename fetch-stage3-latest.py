#!/usr/bin/env python3

from __future__ import absolute_import
from __future__ import print_function
from __future__ import division
from __future__ import unicode_literals

import os
import sys
import time
import errno
import hashlib
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


class InputError(Error):
  """Exception raised for errors in the input."""


class CurlError(Error):
  """Exception raised for curl URL errors."""


class FileNotFoundError(OSError):
  """For when the file or folder does not exist."""


class ChecksumVerifyError(Error):
  """Exception raised when checksum does not match."""


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
    self.old_total_downloaded = 0
    self.systime = 0

  def FindStage3(self):
    url = str(MIRROR + CURRENT_VER)
    destination = BytesIO()
    self._Curl(url, destination)
    response = destination.getvalue()
    ascii_response = response.decode()
    stage3_location = ascii_response.splitlines()[-1].split(' ')[0]
    url = (MIRROR + stage3_location)
    return url

  def _Download(self, working_dir, url):
    filename = url.split('/')[-1]
    destination = working_dir + '/' + filename
    self._Curl(url, destination, filename)
    return destination

  def DownloadStage3(self, working_dir):
    url = self.FindStage3()
    stage3_file = self._Download(working_dir, url)
    digests_url = url + '.DIGESTS'
    digests_file = self._Download(working_dir, digests_url)
    return stage3_file, digests_file

  def _Curl(self, url, destination, filename=None):
    """Handles the bare pyCurl interface.."""
    def _CurlCleanup(destination):
      if os.path.isfile(destination):
        os.remove(destination)
      destination = None

    def _SpawnProgress(total_to_download, total_downloaded, 
                       dummy_total_to_upload, dummy_total_uploaded):
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
          speed = ''
        self.old_total_downloaded = total_downloaded
        percent_completed = float(total_downloaded)/total_to_download
        formatted_percent = format(round((percent_completed * 100),
                                   ndigits=2), '.2f')
        progress = ('%s%%  %s   \r' % (formatted_percent, speed))
        sys.stdout.write(progress)
        sys.stdout.flush()

    def _Humanize(bps):
      gbps = round(((bps / (1024**3)) * 8), ndigits=1)
      if gbps >= 1:
        return (str(gbps) + ' Gb/s')
      mbps = round(((bps / (1024**2)) * 8), ndigits=1)
      if mbps >= 1:
        return (str(mbps) + ' Mb/s')
      kbps = round(((bps / 1024) * 8), ndigits=1)
      if kbps >= 1:
        return (str(kbps) + ' Kb/s')
      # Let's not turn bytes into bits. It's small enough already.
      bps = round(bps, ndigits=1)
      return (str(bps) + ' B/s')

    if filename:
      download_file = open(destination, 'wb')
    curl_handle = pycurl.Curl()
    curl_handle.setopt(pycurl.FOLLOWLOCATION, 1)
    curl_handle.setopt(pycurl.MAXREDIRS, 5)
    curl_handle.setopt(pycurl.CONNECTTIMEOUT, 60)
    curl_handle.setopt(pycurl.TIMEOUT, 300)
    curl_handle.setopt(pycurl.NOSIGNAL, 1)
    try:
      curl_handle.setopt(pycurl.URL, url)
      if filename:
        curl_handle.setopt(pycurl.WRITEDATA, download_file)
        curl_handle.setopt(pycurl.NOPROGRESS, 0)
        curl_handle.setopt(pycurl.PROGRESSFUNCTION, _SpawnProgress)
        print("Downloading %s:" % filename)
      else:
        curl_handle.setopt(pycurl.WRITEDATA, destination)
      curl_handle.perform()
    except pycurl.error as e:
      _CurlCleanup(destination)
      if e.args[0] == 42:
        print('KeyboardInterrupt')
        _CurlCleanup(destination)
        return
      raise CurlError('Download failed: ', e)
    http_code = curl_handle.getinfo(pycurl.HTTP_CODE)
    # if http_code >= 400
      # try another server. use a retry code.
    if http_code < 200 or http_code >= 300:
      _CurlCleanup(destination)
      raise CurlError('Received HTTP error code: ', http_code)
  
    curl_handle.close()
    return destination

  def Verify(self, working_dir, file_to_verify,
             digests, blocksize=32768):
    """Verify the download via mirror-provided '.DIGESTS' file."""
    for location in working_dir, file_to_verify, digests:
      if not os.path.isfile(location) and not os.path.isdir(location):
        raise FileNotFoundError(
            errno.ENOENT, os.strerror(errno.ENOENT), location)
    print('Comparing checksums:')
    sha512 = hashlib.sha512()
    file_handle = open(file_to_verify, 'rb')
    chunk = file_handle.read(blocksize)
    while len(chunk) > 0:
      sha512.update(chunk)
      chunk = file_handle.read(blocksize)
    sha512_sum = sha512.hexdigest()
    digests_handle = open(digests, 'rt+')
    for line in digests_handle:
      if 'SHA512' in line:
        sha512_source = digests_handle.next().split(' ')[0]
        break
    relative_filename = file_to_verify.split('/')[-1]
    relative_digests = digests.split('/')[-1]
    print('\n%s:\n%s...\n%s:\n%s...\n' % 
          (relative_filename, sha512_sum[0:64],
           relative_digests, sha512_source[0:64]))
    if sha512_sum == sha512_source:
      print('SHA512 Checksum verified. :-)')
    else:
      error_str = 'Download checksum failed. See details above.'
      raise ChecksumVerifyError(error_str)


if __name__ == "__main__":
  arguments = ParseArguments()
  download_manager = DownloadManager()
  stage3, digest_file = download_manager.DownloadStage3(arguments.working_dir)
  download_manager.Verify(arguments.working_dir, stage3, digest_file)

