import os
import requests
import time
from html.parser import HTMLParser
from urllib.parse import urljoin

import logging
from logging.handlers import RotatingFileHandler

URL_LIST = [
  'https://tiketore.com/tickets/search?perform_id=42730',
  'https://tiketore.com/tickets/search?perform_id=42731',
  'https://tiketore.com/tickets/search?perform_id=42732',
  'https://tiketore.com/tickets/search?perform_id=42733'
]

# Logger
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
LOG_FILE = 'watcher.log'
SLACK_WEBHOOK_URL = os.environ.get('WATCHER_SLACK_WEBHOOK_URL')
SLACK_USERNAME = os.environ.get('WATCHER_SLACK_USERNAME')

logging.getLogger('requests').setLevel(logging.ERROR)
FORMATTER = logging.Formatter(LOG_FORMAT)
CWD = os.path.dirname(os.path.abspath(__file__))

def getStreamHandler():
  streamHandler = logging.StreamHandler()
  return streamHandler

def getFileHandler(logfile):
  fileHandler = RotatingFileHandler(filename=logfile,
                                     maxBytes=1024 * 1024,
                                     backupCount=9)
  return fileHandler

def getSlackHandler():
  if SLACK_WEBHOOK_URL is None:
    return None
  
  from slack_log_handler import SlackLogHandler
  slack_handler = SlackLogHandler(SLACK_WEBHOOK_URL,
                                  username=SLACK_USERNAME)
  return slack_handler

def getLogger(cwd):
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    streamHandler = getStreamHandler()
    streamHandler.setLevel(logging.INFO)
    streamHandler.setFormatter(FORMATTER)
    logger.addHandler(streamHandler)

    logfile = os.path.join(cwd, LOG_FILE)
    fileHandler = getFileHandler(logfile)
    fileHandler.setLevel(logging.DEBUG)
    fileHandler.setFormatter(FORMATTER)
    logger.addHandler(fileHandler)

    slackHandler = getSlackHandler()
    if slackHandler is not None:
      slackHandler.setLevel(logging.WARN)
      slackHandler.setFormatter(FORMATTER)
      logger.addHandler(slackHandler)

    return logger


class Ticket(object):
  def __init__(self):
    self.title = None
    self.link = None
    self.url = None
    self.status = []

  def __str__(self):
    t = self.title
    t += ''.join('[{status}]'.format(status=s) for s in self.status)
    return t

class TicketoreParser(HTMLParser):
  def __init__(self, url):
    HTMLParser.__init__(self)
    self.state = 'INIT'
    self.tickets = []
    self.activeTicket = None
    self.pageUrl = url

  def hasClass(self, attrs, className):
    classes = []
    if 'class' in attrs:
      classes = [t.strip() for t in attrs['class'].split(' ')]
    return className in classes

  def handle_starttag(self, tag, attrs):
    # print('starttag, state={state}, tag={tag}, attrs={attrs}'
    #       .format(state=self.state, tag=tag, attrs=attrs))
    attrs = dict(attrs)
    if self.state == 'INIT':
      if self.hasClass(attrs, 'list-ticket'):
        self.state = 'TICKET'
        self.activeTicket = Ticket()
    elif self.state == 'TICKET':
      if tag == 'a':
        self.state = 'TICKET_TITLE'
        href = attrs['href']
        self.activeTicket.link = href
        self.activeTicket.url = urljoin(self.pageUrl, href)
      elif tag == 'span' and self.hasClass(attrs, 'badge'):
        self.state = 'TICKET_STATUS'

  def handle_endtag(self, tag):
    # print('endtag, state={state}, tag={tag}'
    #       .format(state=self.state, tag=tag))
    if self.state == 'TICKET':
      if tag == 'small':
        self.tickets.append(self.activeTicket)
        self.state = 'INIT'

  def handle_data(self, data):
    if self.state == 'TICKET_TITLE':
      # print('state={state}, data={data}'
      #       .format(state=self.state, data=data))
      self.activeTicket.title = data
      self.state = 'TICKET'
    elif self.state == 'TICKET_STATUS':
      self.activeTicket.status.append(data.strip())
      self.state = 'TICKET'
      
def findTickets():
  tickets = []
  for url in URL_LIST:
    res = requests.get(url)
    if res.status_code != 200:
      print('http error, status={status_code}'
            .format(status_code=res.status_code))
      continue
    parser = TicketoreParser(url)
    parser.feed(res.text)
    parser.close()
    tickets += parser.tickets
  availableTickets = filter(lambda t: '出品中' in t.status, tickets)
  return list(availableTickets)


def watch(logger):
  while True:
    tickets = findTickets()
    logger.debug('Found {count} tickets'.format(count=len(tickets)))
    for ticket in tickets:
      logger.warn('{title} {url}'
                  .format(title=ticket.title, url=ticket.url))
    time.sleep(60)
    

def main():
  logger = getLogger(CWD)
  logger.debug('Start watching')
  watch(logger)
  logger.debug('Stop watching')

if __name__ == '__main__':
  main()
