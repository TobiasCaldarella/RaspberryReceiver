'''
Created on 25.01.2020

@author: tobias
'''
import smbus
import threading
import time

class PCF8591(object):
    def __init__(self, config):
        '''
        Constructor
        '''
        self.address = config.signal_strength_dac_address
        self.cmd = 0x40
        self.bus = smbus.SMBus(1)
        
    def send(self, value):
        self.bus.write_byte_data(self.address,self.cmd,value)
        
class SignalStrengthMeter(object):
    def __init__(self, coordinator):
        self.t = None
        self.lastValue = None
        self.dac = PCF8591()
        self.run = True
        self.lastAvg = 0
        self.numCollectedValues = 0
        coordinator.signal_strength_meter = self
        
    def init(self):
        self.dac.send(0)

    def enable(self):
        self.run = True
        if self.t is not None:
            return
        self.t = threading.Thread(target=self.processStats)
        self.t.start()
    
    def disable(self):
        self.run = False
        self.t.join()
    
    def processStats(self):
        with open('/proc/net/dev') as f:
            for line in f:
                if 'wlan0' in line and self.run:
                    newValue = int(line.split()[1])
                    if self.lastValue is not None:
                        diff = int((newValue - self.lastValue)/32768*10*256)
                        
                        self.lastAvg = self.numCollectedValues/100*self.lastAvg + (self.numCollectedValues-100)/100*diff
                        if self.numCollectedValues < 99:
                            self.numCollectedValues = self.numCollectedValues + 1
                            
                        self.dac.send(min(int(self.lastAvg),255))
                    self.lastValue = newValue
                    f.seek(0)
                    time.sleep(0.1)
        # write error log, should never ever exit
        self.t = None
                    
                    
                    
        
        
        
        
        