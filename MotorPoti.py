'''
Created on 24.01.2020

@author: tobias
'''

import threading
from GpioController import PowerState, GpioController
import time
import RPi.GPIO as GPIO
from shutil import move

class MotorPoti(object):
    '''
    classdocs
    '''
    def __init__(self, config, coordinator, pwm):
        '''
        Constructor
        '''
        self.pwm = pwm
        self.speed = 100
        self.direction = 0 # 0 ccw, 1 cw
        self.resetTime_ms = config.motorpoti_reset_time_ms
        self.workThread = None
        self.config = config
        self.logger = config.logger
        self.mtx = threading.Lock()
        self.defaultIntervall_ms = config.motorpoti_defaultIntervall_ms
        self.intervall_ms = 0
        self.keep_alive = 0
        coordinator.poti = self
        
    def reset(self):
        with self.mtx:
            self.logger.info("Resetting poti")
            self.intervall_ms = self.resetTime_ms
            self._move(0, 100)

    def set(self, volume_percent, block = False):
        if block:
            self._set(volume_percent)
        else:
            t = threading.Thread(target=lambda: self._set(volume_percent))
            t.start()

    def _set(self, volume_percent):
        with self.mtx:
            self.logger.info("Setting volum to %i", volume_percent)
            self.intervall_ms = self.resetTime_ms
            self._move(0, 100)
            self.mtx.release()
            self.workThread.join()
            self.mtx.acquire()
            self.intervall_ms = self.resetTime_ms*(volume_percent/100)
            self._move(1, 100)
            self.mtx.release()
            self.workThread.join()
            self.mtx.acquire()
        with self.mtx:
            self.logger.info("Setting volum to %i", volume_percent)
            self.intervall_ms = self.resetTime_ms
            self._move(0, 100)
            self.mtx.release()
            self.workThread.join()
            self.mtx.acquire()
            self.intervall_ms = self.resetTime_ms*(volume_percent/100)
            self._move(1, 100)
            self.mtx.release()
            self.workThread.join()
            self.mtx.acquire()
    
    def _move(self, direction, speed):
        self.logger.debug("MotorPoti: move requested")
        if self.workThread:
            self.mtx.release()
            self.logger.debug("MotorPoti: waiting for last issued call")
            self.workThread.join()
            self.mtx.acquire()
            self.logger.debug("MotorPoti: done waiting")
        
        if self.intervall_ms is 0:
            self.intervall_ms = self.defaultIntervall_ms
        self.logger.debug("moving direction: %i, speed %i" % (direction, speed))
        self.keep_alive = 1
        self.direction = direction
        self.speed = speed
        self.workThread = threading.Thread(target=self.do_move)
        self.workThread.start()
        
    def move(self, direction, speed):
        with self.mtx:
            if self.intervall_ms == 0:
                self._move(direction, speed)
            elif self.direction == direction or self.speed == speed:
                self.keep_alive = 1
                self.logger.debug("MotorPoti: already moving, only renewing keep_alive")
            else:
                self.logger.debug("MotorPoti: incompatible speed or direction, discarded")
    
    def moveCCW(self, speed):
        self.move(0, speed)
            
    def moveCW(self, speed):
        self.move(1, speed)
    
    def do_move(self):
        with self.mtx:
            self.logger.debug("MotorPoti: moving started")
            if self.direction == 0:
                self.pwm.pwmAsGpio(pin=self.config.motorpoti_pin_A, state=GPIO.HIGH)
                self.pwm.pwmAsGpio(pin=self.config.motorpoti_pin_B, state=GPIO.LOW)
            else:
                self.pwm.pwmAsGpio(pin=self.config.motorpoti_pin_A, state=GPIO.LOW)
                self.pwm.pwmAsGpio(pin=self.config.motorpoti_pin_B, state=GPIO.HIGH)
                
            self.pwm.pwmPercent(pin=self.config.motorpoti_pin_EN, onPercent=self.speed)
    
            while(self.keep_alive != 0):
                self.logger.debug("MotorPoti: moving in progess")
                self.keep_alive = 0
                self.mtx.release()
                time.sleep(self.intervall_ms/1000)
                self.mtx.acquire()
                
            self.pwm.pwmAsGpio(pin=self.config.motorpoti_pin_EN, state=GPIO.LOW) # power down motor
            self.pwm.pwmAsGpio(pin=self.config.motorpoti_pin_B, state=GPIO.LOW)
            self.pwm.pwmAsGpio(pin=self.config.motorpoti_pin_A, state=GPIO.LOW)
            self.intervall_ms = 0
            self.logger.debug("MotorPoti: moving done")
        
        