'''
Created on 09.08.2019

@author: tobias
'''

from time import sleep
import RPi.GPIO as GPIO
from Configuration import Configuration
from Coordinator import Coordinator
import threading

class Needle(object):
    '''
    classdocs
    '''
    def __init__(self, config: Configuration, coordinator: Coordinator):
        '''
        Constructor
        '''
        coordinator.needle = self
        self.pinA = config.gpio_needle_a
        self.pinB = config.gpio_needle_b
        self.pinC = config.gpio_needle_c
        self.pinD = config.gpio_needle_d
        self.time = config.needle_sleep_time
        self.logger = config.logger
        self.lock = threading.Lock()

        for pin in { self.pinA, self.pinB, self.pinC, self.pinD }:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

    # Schritte 1 - 8 festlegen
    def _Step1(self):
        GPIO.output(self.pinD, True)
        sleep (self.time)
        GPIO.output(self.pinD, False)

    def _Step2(self):
        GPIO.output(self.pinD, True)
        GPIO.output(self.pinC, True)
        sleep (self.time)
        GPIO.output(self.pinD, False)
        GPIO.output(self.pinC, False)

    def _Step3(self):
        GPIO.output(self.pinC, True)
        sleep (self.time)
        GPIO.output(self.pinC, False)

    def _Step4(self):
        GPIO.output(self.pinB, True)
        GPIO.output(self.pinC, True)
        sleep (self.time)
        GPIO.output(self.pinB, False)
        GPIO.output(self.pinC, False)

    def _Step5(self):
        GPIO.output(self.pinB, True)
        sleep (self.time)
        GPIO.output(self.pinB, False)

    def _Step6(self):
        GPIO.output(self.pinA, True)
        GPIO.output(self.pinB, True)
        sleep (self.time)
        GPIO.output(self.pinA, False)
        GPIO.output(self.pinB, False)

    def _Step7(self):
        GPIO.output(self.pinA, True)
        sleep (self.time)
        GPIO.output(self.pinA, False)

    def _Step8(self):
        GPIO.output(self.pinD, True)
        GPIO.output(self.pinA, True)
        sleep (self.time)
        GPIO.output(self.pinD, False)
        GPIO.output(self.pinA, False)

    def moveRight(self, steps: int):
        with self.lock:
            self.logger.debug("Needle moving %i steps right" % steps)
            for i in range (steps):    
                self._Step1()
                self._Step2()
                self._Step3()
                self._Step4()
                self._Step5()
                self._Step6()
                self._Step7()
                self._Step8()
    
    def moveLeft(self, steps: int):
        with self.lock:
            self.logger.debug("Needle moving %i steps left" % steps)
            for i in range (steps):    
                self._Step8()
                self._Step7()
                self._Step6()
                self._Step5()
                self._Step4()
                self._Step3()
                self._Step2()
                self._Step1()
