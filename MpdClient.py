'''
Created on 08.08.2019

@author: tobias
'''

from mpd import MPDClient

class MpdClient(object):
    '''
    classdocs
    '''

    def __init__(self, config):
        '''
        Constructor
        '''
        client = MPDClient()
        client.timeout = 10
        self.client = client
        self.config = config
        
    def connect(self):
        self.client.connect("unix socket?")
        
    def reconnect(self):
        self.client.disconnect()
        self.connect()
    
    def getTracksInRadioPlaylist(self):
        
    def loadPlaylist(self):
        self.client.load(self.config.mpd_radio_playlist)  
        
    def previousTitle(self):
        self.client.previous()
        
    def nextTitle(self):
        self.client.next()  #what if paused?
    