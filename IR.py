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
        
    def disable(self):
        self.logger.debug("IR disabled")
        self.enabled = False
    
    def do_getCode(self):
        coordinator = self.coordinator
        self.logger.debug("...IR connected")
        firstDigit = None
        while self.run is True:
            code = lirc.nextcode()
            if self.enabled is not True:
                continue
            digit = None
            self.logger.debug("got code from IR: '%s'" % code)
            self.disable()
            t = threading.Timer(0.2, lambda: self.enable())
            t.start()
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
            elif "1" in code:
                self.logger.debug("LIRC: '1'")
                digit = 1
            elif "2" in code:
                self.logger.debug("LIRC: '2'")
                digit = 2
            elif "3" in code:
                self.logger.debug("LIRC: '3'")
                digit = 3
            elif "4" in code:
                self.logger.debug("LIRC: '4'")
                digit = 4
            elif "5" in code:
                self.logger.debug("LIRC: '5'")
                digit = 5
            elif "6" in code:
                self.logger.debug("LIRC: '6'")
                digit = 6
            elif "7" in code:
                self.logger.debug("LIRC: '7'")
                digit = 7
            elif "8" in code:
                self.logger.debug("LIRC: '8'")
                digit = 8
            elif "9" in code:
                self.logger.debug("LIRC: '9'")
                digit = 9
            elif "0" in code:
                self.logger.debug("LIRC: '0'")
                digit = 0                
            else:
                self.logger.warn("Received unknown command from LIRC: '%s'" % code)
            if digit is not None:
                if firstDigit is None:
                    firstDigit = digit
                    t = threading.Timer(2.0, lambda: firstDigit=None)
                    t.start()
                else:
                    digit+=(firstDigit*10)
                    firstDigit = None
                    self.coordinator.setChannel(digit)
            else:
                firstDigit = None
            