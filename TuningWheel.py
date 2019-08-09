'''
Created on 09.08.2019

@author: tobias
'''
import Configuration
import Coordinator
from enum import Enum

class Side(Enum):
    NONE= 0
    LEFT = 1
    RIGHT = 2

class TuningWheel(object):
    '''
    classdocs
    '''
    

    def __init__(self, config: Configuration, coordinator: Coordinator):
        '''
        Constructor
        '''
        self.gpio_right_sensor = config.gpio_mag_right
        self.gpio_left_sensor = config.gpio_mag_left
        GPIO.setup(self.gpio_right_ensor, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.gpio_left_sensor, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self.logger = config.logger
        self.lastActiveSide = Side.NONE
        self.coordinator = coordinator
    
        GPIO.add_event_detect(self.gpio_right_sensor, GPIO.BOTH, self.do_right_sensor())
        GPIO.add_event_detect(self.gpio_left_sensor, GPIO.BOTH, self.do_left_sensor())
        
    def do_right_sensor(self):
        if self.lastActiveSide == Side.LEFT:
            self.coordinator.channelUp()
            self.lastActiveSide = Side.RIGHT
    
    def do_left_sensor(self):
        if self.lastActiveSide == Side.RIGHT:
            self.coordinator.channelDown()
            self.lastActiveSide = Side.LEFT
    
    