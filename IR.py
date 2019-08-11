'''
Created on 11.08.2019

@author: tobias
'''
import lirc
import threading

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
        coordinator.ir = self
        self.sockid = lirc.init('RaspberryRadio', 'resources/lircrc')
        self.workerThread = threading.Thread(target=self.do_getCode)
        self.logger.debug("IR initialized")
        self.run = True
        self.enabled = False
       
    def connect(self):
        self.logger.debug("IR connecting...")
        self.workerThread.start()
        
    def enable(self):
        self.logger.debug("IR enabled")
        self.enabled = True
    
    def do_getCode(self):
        coordinator = self.coordinator
        self.logger.debug("...IR connected")
        while self.run is True:
            code = lirc.nextcode()
            if self.enabled is not True:
                continue
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
            
            