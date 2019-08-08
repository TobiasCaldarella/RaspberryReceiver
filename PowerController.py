'''
Created on 07.08.2019

@author: tobias
'''
import RPi.GPIO as GPIO
from enum import Enum
from RaspberryReceiver.Configuration import Configuration
import time
import threading

GPIO.setmode(GPIO.BCM)

class PowerState(Enum):
    ON = 1
    OFF = 2

class PowerController(object):
    '''
    classdocs
    '''

    def __init__(self, config: Configuration):
        '''
        Constructor
        '''
        self.logger = config.logger
        self.gpio_pwr = config.gpio_power
        self.gpio_pwr_btn = config.gpio_pwr_btn
        self.gpio_backlight = config.gpio_backlight
        self.gpio_needle = config.gpio_needle
        self.gpio_stereo = config.gpio_stereo
        self.gpio_speakers = config.gpio_speakers
        
        for pin in [ self.gpio_backlight, self.gpio_needle, self.gpio_stereo ]:
            GPIO.setup(pin, GPIO.OUT, initial = GPIO.LOW)
            
        for pin in [ self.gpio_pwr, self.gpio_speakers ]:
            GPIO.setup(pin, GPIO.OUT, initial = GPIO.HIGH)
        
        for pin in [ self.gpio_pwr_btn ]:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            
        self.backlightPwm = GPIO.PWM(self.gpio_backlight, 50)
        self.stereoPwm = GPIO.PWM(self.gpio_backlight, 50)
        self.backlightPwm.start(0)
        self.stereoPwm.start(0)
        self.backlightState = PowerState.OFF
        self.stereoLightState = PowerState.OFF
        self.stereoBlink = False
        self.stereoBlinkThread = threading.Thread(target=self.do_stereoBlink())
        self.stereoWaitEvent = threading.Event()
        self.stereoLightLock = threading.Lock()
        
    def setPowerAndSpeaker(self, state: PowerState):
        # relais is active on low!
        if state is PowerState.OFF:
            GPIO.output(self.gpio_speakers, GPIO.HIGH)
            time.sleep(0.2)
            GPIO.output(self.gpio_pwr, GPIO.HIGH)
        else:
            GPIO.output(self.gpio_pwr, GPIO.LOW) # enable speakers after 2 seconds
            timer = threading.Timer(2.0, lambda : GPIO.output(self.gpio_speakers, GPIO.LOW))           
            timer.start()
        
    def dimmLight(self, state: PowerState, pwm):
        if state == PowerState.ON:
            r = range(0, 101, 20)
        else:
            r = range(100, -1, -20)
            
        for dc in r:
            pwm.ChangeDutyCycle(dc)
            time.sleep(0.1)
        
    def setBacklight(self, state: PowerState):
        if state == self.backlightState:
            return
        self.backlightState = state
        self.dimmLight(state, self.gpio_backlight)
        
    def setStereolight(self, state: PowerState, blinking = False):
        self.stereoBlink = blinking # todo: cancel thread!
        if state == self.stereoLightState: # already transiting to the desired state? don't wait!
            return
        self.stereoLightLock.acquire()
        if state == self.stereoLightState:
            return
        self.stereoLightState = state
        self.dimmLight(state, self.gpio_stereo)
        self.stereoLightLock.release()
        
    def do_stereoBlink(self):
        while True:
            if self.stereoBlink is True:
                self.setStereolight(PowerState.ON, blinking=True)
            if self.stereoBlink is True:
                self.setStereolight(PowerState.OFF, blinking=True)
            self.stereoWaitEvent.wait(10)
            
    def setStereoBlink(self, active=False):
        if self.stereoBlink == active:
            return
        
        self.stereoBlink = active
        if active is True:
            self.stereoWaitEvent.set()
        
        