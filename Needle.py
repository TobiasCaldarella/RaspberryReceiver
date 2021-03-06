'''
Created on 09.08.2019

@author: tobias
'''

from time import sleep
import RPi.GPIO as GPIO
from Configuration import Configuration
from Coordinator import Coordinator
import threading
from threading import Thread, Semaphore, Lock

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
        self.numChannels = 0
        self.stepsPerChannel = 0
        self.leftMargin = config.needle_left_margin
        self.numSteps = config.needle_steps
        self.currentPosition = None
        self.desiredPosition = None
        self.desiredChannel = 0
        self.mtx = Lock()
        self.isMoving = False
        self.interrupted = False

        for pin in { self.pinA, self.pinB, self.pinC, self.pinD }:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

    def init(self, numChannels):
        self.numChannels = numChannels
        self.currentPosition = self.numSteps # worst case: needle at rightmost position
        self.desiredPosition = 0 # move to leftmost position to be in defined position         
        self.stepsPerChannel = int((self.numSteps-self.leftMargin)/self.numChannels)
        self.logger.debug("%i needleStepsPerChannel" % self.stepsPerChannel)
        self.setNeedleForChannel(ch=None, relative=False) # ch=None since we explicitly set the position before
        
    def interrupt_set(self):
        with self.mtx:
            self.interrupted = True
            if self.isMoving is False:
                return
            self.logger.info("Needle: interrupting")
            self.desiredPosition = None
            
    def interrupt_clear(self):
        with self.mtx:
            self.interrupted = False
        
    def updateIfNeedleMoving(self, ch, relative):
        with self.mtx:
            if relative is True:
                ch = self.desiredChannel + ch
            if ch is not None:
                self.logger.debug("Setting needle to channel %i (absolute)", ch)
            if ch is not None and (ch < 0 or ch >= self.numChannels):
                self.logger.warn("setNeedleForChannel(%i): invalid channel" % ch)
                return False
            
            if not self.isMoving:
                return False #cannot update if not moving
            else:
                if ch is not None:
                    self.desiredPosition = (ch * self.stepsPerChannel) + self.leftMargin
                    self.desiredChannel = ch
                return True
        
    def setNeedleForChannel(self, ch, relative):
        with self.mtx:
            #eventually return channel to see if it changed in the meantime? 
            if self.interrupted:
                return None # interrupt requested, return immediately
            if relative is True:
                ch = self.desiredChannel + ch
            if ch is not None:
                self.logger.debug("Setting needle to channel %i (absolute)", ch)
            if ch is not None and (ch < 0 or ch >= self.numChannels):
                self.logger.warn("setNeedleForChannel(%i): invalid channel" % ch)
                return self.desiredChannel
            
            if self.isMoving:
                self.logger.error("Already moving, refusing another drivingThread!")
                return None
            self.isMoving = True
            
            if ch is not None:
                self.desiredPosition = (ch * self.stepsPerChannel) + self.leftMargin
                self.desiredChannel = ch
            else:
                ch = -1
            self.logger.debug("needle requested at channel %i. Current: %i target: %i" % (ch, self.currentPosition, self.desiredPosition))
            self.logger.debug("we are driving thread, start moving")
            while (self.currentPosition != self.desiredPosition and self.desiredPosition is not None):
                try:
                    self.mtx.release()
                    self._adjustNeedle()
                finally:
                    self.mtx.acquire()
                    
            self.isMoving = False
            self.logger.debug("needle in desired position, exiting")
            return self.desiredChannel
    
    def _adjustNeedle(self):
        self.logger.info("Moving needle from %i to %i..." % (self.currentPosition, self.desiredPosition))
        curDesiredPosition = self.desiredPosition
        while (self.currentPosition != self.desiredPosition):
            if curDesiredPosition != self.desiredPosition:
                if self.desiredPosition is None:
                    self.logger.debug("interrupted! needle at %i" % self.currentPosition)
                    return
                self.logger.debug("desiredPosition changed from %i to %i" % (curDesiredPosition, self.desiredPosition))
                curDesiredPosition = self.desiredPosition
                
            if self.desiredPosition > self.currentPosition:
                self._moveRight()
            else:
                self._moveLeft()
        self.logger.info("Needle at %i" % self.currentPosition)

    def _moveRight(self):
        self._Step1()
        self._Step2()
        self._Step3()
        self._Step4()
        self._Step5()
        self._Step6()
        self._Step7()
        self._Step8()
        self.currentPosition+=1
    
    def _moveLeft(self):   
        self._Step8()
        self._Step7()
        self._Step6()
        self._Step5()
        self._Step4()
        self._Step3()
        self._Step2()
        self._Step1()
        self.currentPosition-=1
        
    # Schritte 1 - 8 festlegen
    def _Step1(self):
        GPIO.output(self.pinB, True)
        sleep (self.time)
        GPIO.output(self.pinB, False)

    def _Step2(self):
        GPIO.output(self.pinB, True)
        GPIO.output(self.pinD, True)
        sleep (self.time)
        GPIO.output(self.pinB, False)
        GPIO.output(self.pinD, False)

    def _Step3(self):
        GPIO.output(self.pinD, True)
        sleep (self.time)
        GPIO.output(self.pinD, False)

    def _Step4(self):
        GPIO.output(self.pinA, True)
        GPIO.output(self.pinD, True)
        sleep (self.time)
        GPIO.output(self.pinA, False)
        GPIO.output(self.pinD, False)

    def _Step5(self):
        GPIO.output(self.pinA, True)
        sleep (self.time)
        GPIO.output(self.pinA, False)

    def _Step6(self):
        GPIO.output(self.pinA, True)
        GPIO.output(self.pinC, True)
        sleep (self.time)
        GPIO.output(self.pinA, False)
        GPIO.output(self.pinC, False)

    def _Step7(self):
        GPIO.output(self.pinC, True)
        sleep (self.time)
        GPIO.output(self.pinC, False)

    def _Step8(self):
        GPIO.output(self.pinC, True)
        GPIO.output(self.pinB, True)
        sleep (self.time)
        GPIO.output(self.pinC, False)
        GPIO.output(self.pinB, False)
