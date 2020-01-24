'''
Created on 11.08.2019

@author: tobias
'''
import lirc
import threading
import multiprocessing
from Configuration import _RadioPowerState

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
        #self.sockid = lirc.init('RaspberryRadio', 'resources/lircrc')
        self.workerThread = threading.Thread(target=self.do_getCode)
        self.logger.info("IR initialized")
        self.enabled = False
        self.firstDigit = None
        self.two_digit_timeout = None
        self.sleep_timeout = None
        self.twoDigitLock = threading.Lock()
        self.twoDigitHandler = self.setChannelAtCoordinator
        self.codeQueue = multiprocessing.Queue()
        #self.lircProcess = multiprocessing.Process(target=self.p_nextcode,args=(self.codeQueue,))
       
    def connect(self):
        self.logger.debug("IR connecting...")
        self.run = True

        self.workerThread.start()
        #self.lircProcess.start()
        
    def disconnect(self):
        self.logger.debug("IR disconnecting...")
        self.run = False
        #self.lircProcess.terminate()
        #lirc.deinit()
        if self.workerThread.join(timeout=10):
            self.logger.info("IR disconnected and stopped")
        else:
            self.logger.error("Error disconnecting IR!")
        
    def enable(self):
        self.logger.info("IR enabled")
        self.enabled = True
        
    def disable(self):
        self.logger.info("IR disabled")
        self.enabled = False
    
    def setChannelAtCoordinator(self, channel):
        self.coordinator.setChannel(channel = channel - 1, relative = False, setIfPowerOff = True) # channel starts at 0!
        self.coordinator.powerOn()
    
    def do_two_digit_timeout(self):
        with self.twoDigitLock:
            if self.firstDigit is not None:
                self.logger.info("Two digit input timed out. Assuming %i" % self.firstDigit)
                ch = self.firstDigit
                self.finish_two_digit_input(ch)
            else:
                self.logger.info("Two digit input timed out w/o input. Cancelled")
                self.cancel_two_digit_input()
                
    def cancel_two_digit_input(self):
        self.logger.info("Two digit input cancelled")
        if self.two_digit_timeout:
            self.two_digit_timeout.cancel()
        self.coordinator.invertNeedleLightState(restore=True)
        self.firstDigit = None
        self.twoDigitHandler = self.setChannelAtCoordinator
    
    def finish_two_digit_input(self, value):
        if value is None:
            self.logger.debug("Two digit input finished without number")
            return
        self.logger.debug("Two digit input finished: '%i'" % value)
        self.firstDigit = None
        if self.two_digit_timeout:
            self.two_digit_timeout.cancel()
        self.coordinator.invertNeedleLightState(restore=True)
        self.twoDigitHandler(value)
        self.twoDigitHandler = self.setChannelAtCoordinator
        
    def p_nextcode(self, queue):
        while True:
            code = lirc.nextcode()
            queue.put(code)
            
    def do_getCode(self):
        coordinator = self.coordinator
        self.logger.debug("...IR connected")
        with lirc.LircdConnection('RaspberryRadio', 'resources/lircrc', lirc.client.get_default_socket_path()) as conn:
            while self.run is True:
                code = conn.readline()
                self.logger.debug("got code from IR: '%s'" % code)
                if self.enabled is not True:
                    self.logger.debug("IR not enabled, ignored")
                    continue
                digit = None
                #self.disable()
                #t = threading.Timer(0.2, self.enable)
                #t.start()
                if "power" in code:
                    self.logger.info("LIRC: 'power'")
                    if coordinator.powerState == _RadioPowerState.POWERED_UP or coordinator.powerState == _RadioPowerState.POWERING_DOWN:
                        coordinator.powerOff()
                    else:
                        coordinator.powerOn()
                    continue
                elif "channel_up" in code:
                    self.logger.info("LIRC: 'channel_up'")
                    coordinator.setChannel(channel=1, relative=True)
                    continue
                elif "channel_down" in code:
                    self.logger.info("LIRC: 'channel_down'")
                    coordinator.setChannel(channel=-1, relative=True)
                    continue
                elif "volume_up" in code:
                    self.logger.info("LIRC: 'volume_up'")
                    coordinator.volumeUp()
                    continue
                elif "volume_down" in code:
                    self.logger.info("LIRC: 'volume_down'")
                    coordinator.volumeDown()
                    continue
                elif "1" in code:
                    self.logger.info("LIRC: '1'")
                    digit = 1
                elif "2" in code:
                    self.logger.info("LIRC: '2'")
                    digit = 2
                elif "3" in code:
                    self.logger.info("LIRC: '3'")
                    digit = 3
                elif "4" in code:
                    self.logger.info("LIRC: '4'")
                    digit = 4
                elif "5" in code:
                    self.logger.info("LIRC: '5'")
                    digit = 5
                elif "6" in code:
                    self.logger.info("LIRC: '6'")
                    digit = 6
                elif "7" in code:
                    self.logger.info("LIRC: '7'")
                    digit = 7
                elif "8" in code:
                    self.logger.info("LIRC: '8'")
                    digit = 8
                elif "9" in code:
                    self.logger.info("LIRC: '9'")
                    digit = 9
                elif "0" in code:
                    self.logger.info("LIRC: '0'")
                    digit = 0
                elif "ok" in code:
                    self.logger.info("LIRC: 'ok'")
                    with self.twoDigitLock:
                        self.finish_two_digit_input(self.firstDigit)
                elif "esc" in code:
                    self.logger.info("LIRC: 'esc'")
                    pass
                elif "mute" in code:
                    self.logger.info("LIRC: 'mute'")
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
                            self.logger.info("LIRC: first digit: %i" % digit)
                            self.firstDigit = digit
                            self.coordinator.invertNeedleLightState()
                            self.two_digit_timeout = threading.Timer(2.0, self.do_two_digit_timeout)
                            self.two_digit_timeout.start()
                        else:
                            self.two_digit_timeout.cancel()
                            digit+=(self.firstDigit*10)
                            self.logger.info("LIRC: two digit value: %i" % digit)
                            self.finish_two_digit_input(digit)
                    else:
                        self.cancel_two_digit_input()
            