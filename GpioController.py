'''
Created on 07.08.2019

@author: tobias
'''
import RPi.GPIO as GPIO
from enum import Enum
import Configuration
import time
import threading
import Coordinator

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
        self.logger.info("GpioController initializing...")
        self.gpio_pwr = config.gpio_power
        self.gpio_pwr_btn = config.gpio_pwr_btn
        self.gpio_backlight = config.gpio_backlight
        self.gpio_needle = config.gpio_needle
        self.gpio_stereo = config.gpio_stereo
        self.gpio_speakers = config.gpio_speakers
        self.coordinator = coordinator
        coordinator.gpioController = self
        
        for pin in [ self.gpio_backlight, self.gpio_needle, self.gpio_stereo, self.gpio_speakers ]:
            if pin is not None:
                GPIO.setup(pin, GPIO.OUT, initial = GPIO.LOW)
            
        for pin in [ self.gpio_pwr ]:
            if pin is not None:
                GPIO.setup(pin, GPIO.OUT, initial = GPIO.HIGH)
        
        for pin in [ self.gpio_pwr_btn ]:
            if pin is not None:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            
        if self.gpio_backlight is not None:
            self.backlightPwm = GPIO.PWM(self.gpio_backlight, 50)
            self.backlightPwm.start(0)
        if self.gpio_stereo is not None:
            self.stereoPwm = GPIO.PWM(self.gpio_stereo, 50)
            self.stereoPwm.start(0)
        
        self.backlightState = PowerState.OFF
        self.stereoLightState = PowerState.OFF
        self.stereoBlink = False
        self.stereoBlinkPause_s = 10
        self.stereoWaitEvent = threading.Event()
        self.stereoLightLock = threading.Lock()
        self.stereoBlinkThread = threading.Thread(target=self.do_stereoBlink)
        self.stereoBlinkThread.start()
        self.logger.info("GpioController initialized")
        
    def setPowerAndSpeaker(self, state: PowerState):
        # relais is active on low!
        if state is PowerState.OFF:
            if self.gpio_speakers is not None:
                GPIO.output(self.gpio_speakers, GPIO.LOW)
                self.logger.debug("Speakers off")
                time.sleep(0.5)
            GPIO.output(self.gpio_pwr, GPIO.HIGH) # active on low!
            time.sleep(1.0)
        else:
            GPIO.output(self.gpio_pwr, GPIO.LOW) # active on low!
            time.sleep(2.0)
            if self.gpio_speakers is not None:
                GPIO.output(self.gpio_speakers, GPIO.HIGH)
                self.logger.debug("Speakers on")
        
    def dimmLight(self, state: PowerState, pwm, steps=5):
        if state == PowerState.ON:
            if steps > 0:
                r = range(0, 100, int(100/steps))
                for dc in r:
                    pwm.ChangeDutyCycle(dc)
                    time.sleep(0.1)
            pwm.ChangeDutyCycle(100)
        else:
            if steps > 0:
                r = range(100, 0, -int(100/steps))
                for dc in r:
                    pwm.ChangeDutyCycle(dc)
                    time.sleep(0.1)
            pwm.ChangeDutyCycle(0)
        
    def setBacklight(self, state: PowerState):
        if self.gpio_backlight is None:
            return
        if state == self.backlightState:
            return
        self.backlightState = state
        self.dimmLight(state, self.backlightPwm)
        
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
            if blinking is False:
                self.dimmLight(state, self.stereoPwm, 0)
            else:
                self.dimmLight(state, self.stereoPwm)
        
    def do_stereoBlink(self):
        while True:
            if self.stereoBlink is True:
                self.setStereolight(PowerState.ON, blinking=True)
            if self.stereoBlink is True:
                self.setStereolight(PowerState.OFF, blinking=True)
            self.stereoWaitEvent.wait(self.stereoBlinkPause_s)
            self.stereoWaitEvent.clear()
            
    def setStereoBlink(self, active=False, pause_s = 0):
        self.logger.debug("StereoLight blink set to %s, pause %i" %(active, pause_s))
        
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
    
    def enable_power_button(self):
        self.logger.debug("Power button enabled")
        GPIO.add_event_detect(self.gpio_pwr_btn, GPIO.FALLING, callback=self.do_power_button, bouncetime=300)    
    
    def disable_power_button(self):
        self.logger.debug("Power button disabled")
        GPIO.remove_event_detect(self.gpio_pwr_btn)
        
    def do_power_button(self, ch):
        self.logger.debug("Power button pressed!")
        if self.coordinator.isPoweredOn() is True:
            self.coordinator.powerOff()
        else:
            self.coordinator.powerOn()
        