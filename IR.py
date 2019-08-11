'''
Created on 11.08.2019

@author: tobias
'''
import lirc
import threading
from main import coordinator

class IR(object):
    '''
    classdocs
    '''

    def __init__(self, config, coordinator):
        '''
        Constructor
        '''
        self.logger = config.logger
        self.coordinator = coordinator
        self.sockid = lirc.init('RaspberryRadio', 'resources/lircrc')
        self.workerThread = threading.Thread(target=self.do_getCode)
        self.logger.debug("IR initialized")
        self.run = True
       
    def connect(self):
        self.logger.debug("IR connecting...")
        self.workerThread.start()
        
    def do_getCode(self):
        self.logger.debug("...IR connected")
        while self.run is True:
            code = lirc.nextcode()
            self.logger.debug("got code from IR: '%s'" % code)
            if "power" in code:
                self.logger.info("LIRC: 'power'")
                if coordinator.isPoweredOn() is True:
                    coordinator.powerOff()
                else:
                    coordinator.powerOn()
            elif "channel_up" in code:
                self.logger.debug("LIRC: 'channel_up'")
                coordinator.channelUp()
            elif "channel_down" in code:
                self.logger.debug("LIRC: 'channel_down'")
                coordinator.channelDown()
            elif "volume_up" in code:
                self.logger.debug("LIRC: 'volume_up'")
                pass
            elif "volume_down" in code:
                self.logger.debug("LIRC: 'volume_down'")
                pass
            else:
                self.logger.warn("Received unknown command from LIRC: '%s'" % code)
            
            