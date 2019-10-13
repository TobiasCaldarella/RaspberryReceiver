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
        self.lock = threading.Lock()
        self.numChannels = 0
        self.stepsPerChannel = 0
        self.leftMargin = config.needle_left_margin
        self.numSteps = config.needle_steps
        self.currentPosition = None
        self.desiredPosition = None
        self.run = True
        self.workerThread = Thread(target=self._workerFct)
        self.semaphore = Semaphore(value=1)
        self.mtx = Lock()
        self.callback = None

        for pin in { self.pinA, self.pinB, self.pinC, self.pinD }:
            GPIO.setup(pin, GPIO.OUT)
            GPIO.output(pin, GPIO.LOW)

    def init(self, numChannels):
        self.numChannels = numChannels
        self.currentPosition = self.numSteps # worst case: needle at rightmost position
        self.desiredPosition = 0 # move to leftmost position to be in defined position         
        self.stepsPerChannel = int((self.numSteps-self.leftMargin)/self.numChannels)
        self.logger.debug("%i needleStepsPerChannel" % self.stepsPerChannel)
        self.workerThread.start() # will adjust the needle immediately since semaphore is initially in released state
        
    def stop(self):
        self.logger.debug("waiting for worker thread to stop...")
        self.run = False
        self.semaphore.release()
        self.workerThread.join()
        self.logger.debug("...thread stopped!")
        
    def setNeedleForChannel(self, ch: int, cb=None):   
        if ch < 0 or ch > self.numChannels:
            self.logger.warn("setNeedleForChannel(%i): invalid channel" % ch)
            return
        
        with self.mtx:
            self.desiredPosition = (ch * self.stepsPerChannel) + self.leftMargin
            self.logger.debug("needle requested at channel %i. Current: %i target: %i" % (ch, self.currentPosition, self.desiredPosition))
            self.callback = cb
            self.semaphore.release()
    
    def _workerFct(self):
        self.logger.debug("Worker thread started")
        while self.run:
            self.logger.debug("...waiting for needle desired position update...")
            self.semaphore.acquire()
            self.logger.debug("got update")
            with self.mtx:
                while (self.currentPosition != self.desiredPosition):
                    self.mtx.release()
                    self._adjustNeedle()
                    self.mtx.acquire()
                if self.callback:
                    self.logger.debug("needle in desired position, issuing callback")
                    self.callback()
                    self.callback = None
                    
        self.logger.debug("Worker thread ended")

    def _adjustNeedle(self):
        self.logger.info("Moving needle from %i to %i..." % (self.currentPosition, self.desiredPosition))
        curDesiredPosition = self.desiredPosition
        while (self.currentPosition != self.desiredPosition):
            if curDesiredPosition != self.desiredPosition:
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
