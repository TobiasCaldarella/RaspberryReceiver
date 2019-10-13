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
        self.enabled = False
        self.firstDigit = None
        self.two_digit_timeout = None
        self.sleep_timeout = None
        self.twoDigitLock = threading.Lock()
        self.twoDigitHandler = self.setChannel
       
    def connect(self):
        self.logger.debug("IR connecting...")
        self.run = True
        self.workerThread.start()
        
    def disconnect(self):
        self.logger.debug("IR disconnecting...")
        self.run = False
        lirc.deinit()
        if self.workerThread.join(timeout=10):
            self.logger.info("IR disconnected and stopped")
        else:
            self.logger.error("Error disconnecting IR!")
        
    def enable(self):
        self.logger.debug("IR enabled")
        self.enabled = True
        
    def disable(self):
        self.logger.debug("IR disabled")
        self.enabled = False
    
    def setChannelAtCoordinator(self, channel):
        self.coordinator.setChannel(channel - 1) # channel starts at 0!
    
    def do_two_digit_timeout(self):
        with self.twoDigitLock:
            if self.firstDigit is not None:
                self.logger.debug("Two digit input timed out. Assuming %i" % self.firstDigit)
                ch = self.firstDigit
                self.finish_two_digit_input(ch)
            else:
                self.logger.debug("Two digit input timed out w/o input. Cancelled")
                self.cancel_two_digit_input()
                
    def cancel_two_digit_input(self):
        self.logger.debug("Two digit input cancelled")
        if self.two_digit_timeout:
            self.two_digit_timeout.cancel()
        self.firstDigit = None
        self.twoDigitHandler = self.setChannel
    
    def finish_two_digit_input(self, input):
        self.logger.debug("Two digit input finished: '%i'" % input)
        self.firstDigit = None
        if self.two_digit_timeout:
            self.two_digit_timeout.cancel()
        self.twoDigitHandler(input)
        self.twoDigitHandler = self.setChannel
    
    def do_getCode(self):
        coordinator = self.coordinator
        self.logger.debug("...IR connected")
        while self.run is True:
            code = lirc.nextcode()
            if self.enabled is not True:
                continue
            digit = None
            self.logger.debug("got code from IR: '%s'" % code)
            #self.disable()
            #t = threading.Timer(0.2, self.enable)
            #t.start()
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
                coordinator.volumeUp()
                pass
            elif "volume_down" in code:
                self.logger.debug("LIRC: 'volume_down'")
                coordinator.volumeDown()
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
            elif "ok" in code:
                self.logger.debug("LIRC: 'ok'")
                with self.twoDigitLock:
                    self.finish_two_digit_input(self.firstDigit)
            elif "esc" in code:
                self.logger.debug("LIRC: 'esc'")
                pass
            elif "mute" in code:
                self.logger.debug("LIRC: 'mute'")
                with self.twoDigitLock:
                    self.cancel_two_digit_input()
                    self.coordinator.sleep(0) # cancel old sleep
                    self.twoDigitHandler = self.coordinator.sleep
                    self.two_digit_timeout = threading.Timer(10.0, self.do_two_digit_timeout)
                    self.two_digit_timeout.start()
                    continue
            else:
                self.logger.warn("Received unknown command from LIRC: '%s'" % code)
                continue
                
            with self.twoDigitLock:
                if digit is not None:
                    if self.firstDigit is None:
                        self.logger.debug("LIRC: first digit: %i" % digit)
                        self.firstDigit = digit
                        self.two_digit_timeout = threading.Timer(2.0, self.do_two_digit_timeout)
                        self.two_digit_timeout.start()
                    else:
                        self.two_digit_timeout.cancel()
                        digit+=(self.firstDigit*10)
                        self.logger.debug("LIRC: two digit value: %i" % digit)
                        self.finish_two_digit_input(digit)
                else:
                    self.cancel_two_digit_input()
            