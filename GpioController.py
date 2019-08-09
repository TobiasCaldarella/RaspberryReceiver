'''
Created on 07.08.2019

@author: tobias
'''
import RPi.GPIO as GPIO
from enum import Enum
import Configuration
import time
import threading
from Coordinator import Coordinator

GPIO.setmode(GPIO.BCM)

class PowerState(Enum):
    ON = 1
    OFF = 2

class GpioController(object):
    '''
    classdocs
    '''
    
    # todo: pwr button must trigger coordinator action

    def __init__(self, config: Configuration, coordinator: Coordinator):
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
        self.coordinator = coordinator
        coordinator.gpioController = self
        
        for pin in [ self.gpio_backlight, self.gpio_needle, self.gpio_stereo ]:
            if pin is not None:
                GPIO.setup(pin, GPIO.OUT, initial = GPIO.LOW)
            
        for pin in [ self.gpio_pwr, self.gpio_speakers ]:
            if pin is not None:
                GPIO.setup(pin, GPIO.OUT, initial = GPIO.HIGH)
        
        for pin in [ self.gpio_pwr_btn ]:
            if pin is not None:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            
        if self.gpio_backlight is not None:
            self.backlightPwm = GPIO.PWM(self.gpio_backlight, 50)
            self.backlightPwm.start(0)
        if self.gpio_stereo is not None:
            self.stereoPwm = GPIO.PWM(self.gpio_backlight, 50)
            self.stereoPwm.start(0)
        self.backlightState = PowerState.OFF
        self.stereoLightState = PowerState.OFF
        self.stereoBlink = False
        self.stereoBlinkPause_s = 10
        self.stereoBlinkThread = threading.Thread(target=self.do_stereoBlink())
        self.stereoWaitEvent = threading.Event()
        self.stereoLightLock = threading.Lock()
        
    def setPowerAndSpeaker(self, state: PowerState):
        # relais is active on low!
        if state is PowerState.OFF:
            if self.gpio_speakers is not None:
                GPIO.output(self.gpio_speakers, GPIO.HIGH)
                time.sleep(0.2)
            GPIO.output(self.gpio_pwr, GPIO.HIGH)
        else:
            GPIO.output(self.gpio_pwr, GPIO.LOW) # enable speakers after 2 seconds
            if self.gpio_speakers is not None:
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
        if self.gpio_backlight is None:
            return
        if state == self.backlightState:
            return
        self.backlightState = state
        self.dimmLight(state, self.gpio_backlight)
        
    def setStereolight(self, state: PowerState, blinking = False):
        if self.gpio_stereo is None:
            return
        self.stereoBlink = blinking
        if state == self.stereoLightState: # already transiting to the desired state? don't wait!
            return
        with self.stereoLightLock:
            if state == self.stereoLightState:
                return
            self.stereoLightState = state
            self.dimmLight(state, self.gpio_stereo)
        
    def do_stereoBlink(self):
        while True:
            if self.stereoBlink is True:
                self.setStereolight(PowerState.ON, blinking=True)
            if self.stereoBlink is True:
                self.setStereolight(PowerState.OFF, blinking=True)
            self.stereoWaitEvent.wait(self.stereoBlinkPause_s)
            
    def setStereoBlink(self, active=False, pause_s = 0):
        if self.stereoBlink == active:
            return
        
        self.stereoBlink = active
        if active is True:
            self.stereoBlinkPause_s = pause_s
            self.stereoWaitEvent.set()
        
    def setNeedlelight(self, state: PowerState):
        if self.gpio_needle is None:
            return
        if state is PowerState.ON:
            gpioState = GPIO.HIGH
        else:
            gpioState = GPIO.LOW
        GPIO.output(self.gpio_needle, gpioState)
        