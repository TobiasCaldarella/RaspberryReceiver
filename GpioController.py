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
import Adafruit_PCA9685
from Configuration import _RadioPowerState

class PowerState(Enum):
    ON = 1
    OFF = 2

    
class Light(object):
    
    def __init__(self, ctr, pin, fadeSteps):
        self.ctr = ctr
        self.pin = pin
        self.mtx = threading.Lock()
        self.fadeSteps = fadeSteps
        self.state = PowerState.OFF
        self.blinking = False
    
    def on(self):
        if self.state is PowerState.ON:
            return
        
        self.ctr.fade(self.pin, 0, 100, self.fadeSteps)
        

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
        self.pin_pwr = config.pin_power
        self.gpio_pwr_btn = config.gpio_pwr_btn
        self.pin_backlight = config.gpio_backlight
        self.pin_needle = config.pin_needle
        self.pin_stereo = config.pin_stereo
        self.pin_speakers = config.pin_speakers
        
        self.pwm = Adafruit_PCA9685.PCA9685(address=0x40)
        self.pwm.set_pwm_freq(5000)
        
        self.coordinator = coordinator
        coordinator.gpioController = self
        
        #for pin in [ self.gpio_backlight, self.gpio_needle, self.gpio_stereo, self.gpio_speakers ]:
        #    if pin is not None:
        #        GPIO.setup(pin, GPIO.OUT, initial = GPIO.LOW)
            
        #for pin in [ self.gpio_pwr ]:
        #    if pin is not None:
        #        GPIO.setup(pin, GPIO.OUT, initial = GPIO.HIGH)
        
        for pin in [ self.gpio_pwr_btn ]:
            if pin is not None:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        self.needleLightState = PowerState.OFF
        self.backlightState = PowerState.OFF
        self.backlightIntensity = 0
        self.backlightDefaultIntensity = config.backlight_default_brightness
        self.stereoLightState = PowerState.OFF
        self.stereoLightIntensity = 0
        self.stereoLightDefaultIntensity = config.stereo_default_brightness
        self.stereoBlink = False
        self.stereoBlinkPause_s = 10
        self.stereoWaitEvent = threading.Event()
        self.stereoLightLock = threading.Lock()
        self.stereoBlinkThread = threading.Thread(target=self.do_stereoBlink)
        self.stereoBlinkThread.start()
        self.logger.info("GpioController initialized")
        
    def pwmAsGpio(self, pin, state):
        if state is GPIO.HIGH:
            self.pwm.set_pwm(pin, 0, 0)
        else:
            self.pwm.set_pwm(pin, 0, 4095)
            
    def pwmPercent(self, pin, onPercent):
        self.pwm.set_pwm(pin, 4095-(onPercent/100*4095), 4095)
        
    def setPowerAndSpeaker(self, state: PowerState):
        # relais is active on low!
        if state is PowerState.OFF:
            if self.gpio_speakers is not None:
                self.pwmAsGpio(self.pin_speakers, GPIO.LOW)
                self.logger.debug("Speakers off")
                time.sleep(0.5)
            self.pwmAsGpio(self.pin_pwr, GPIO.LOW)
            self.logger.info("Powered down")
            time.sleep(1.0)
        else:
            self.pwmAsGpio(self.pin_pwr, GPIO.HIGH)
            self.logger.info("Powered up")
            time.sleep(3.0)
            if self.gpio_speakers is not None:
                self.pwmAsGpio(self.pin_speakers, GPIO.HIGH)
                self.logger.debug("Speakers on")
        
    def dimmLight(self, state: PowerState, pin, steps=10):
        if state == PowerState.ON:
            if steps > 0:
                r = range(0, 100, int(100/steps))
                for dc in r:
                    self.pwmPercent(pin, dc)
                    time.sleep(0.05)
                self.pwmPercent(pin, 100)
        else:
            if steps > 0:
                r = range(4095, 0, -int(4095/steps))
                for dc in r:
                    self.pwmPercent(pin, dc)
                    time.sleep(0.05)
            self.pwmPercent(pin, 0)
    
    def fade(self, pin, current, target, steps):
        if pin is None:
            return
        if current == target:
            return

        if steps > 0:
            step = (target - current)/steps
            while steps > 0:
                current = current + step
                self.pwmPercent(pin, current)
                time.sleep(0.05)
                steps = steps - 1
        self.pwmPercent(pin, target)
    
    def dimmLightNew(self, pin, current, target, steps=10):
        if pin is None:
            return
        if current == target:
            return

        if steps > 0:
            step = (target - current)/steps
            while steps > 0:
                current = current + step
                self.pwmPercent(pin, current)
                time.sleep(0.05)
                steps = steps - 1
        self.pwmPercent(pin, target)
        
    def setBacklight(self, state = None, intensity = None):
        if self.gpio_backlight is None:
            return
        if intensity is None:
            if state is PowerState.ON:
                intensity = self.backlightDefaultIntensity
            else:
                intensity = 0
        if state is None:
            state = self.backlightState
        
        if state is not PowerState.ON:
            intensity = 0
            
        self.dimmLightNew(self.pin_backlight, self.backlightIntensity, intensity)
        self.backlightIntensity = intensity
        self.backlightState = state
        
    def setStereolight(self, state: PowerState, blinking = False):
        if self.gpio_stereo is None:
            return
        with self.stereoLightLock:
            self.stereoBlink = blinking
            if state == self.stereoLightState: # already transiting to the desired state? don't wait!
                return
            if state is PowerState.ON:
                intensity = self.stereoLightDefaultIntensity
            else:
                intensity = 0
                
            if blinking is False:
                self.dimmLightNew(self.pin_stereo, self.stereoLightIntensity, intensity, 0) # 0steps
            else:
                self.dimmLightNew(self.pin_stereo, self.stereoLightIntensity, intensity) # default number of steps
            
            self.stereoLightState = state
            self.stereoLightIntensity = intensity
        
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
            
        self.pwmAsGpio(self.pin_needle, gpioState)
        self.needleLightState = state
            
    def enable_power_button(self):
        self.logger.debug("Power button enabled")
        GPIO.add_event_detect(self.gpio_pwr_btn, GPIO.FALLING, callback=self.do_power_button, bouncetime=300)    
    
    def disable_power_button(self):
        self.logger.debug("Power button disabled")
        GPIO.remove_event_detect(self.gpio_pwr_btn)
        
    def do_power_button(self, ch):
        if GPIO.input(self.gpio_pwr_btn) != GPIO.LOW:
            self.logger.debug("Spurious power button interrupt, ignored.")
            return
        self.logger.debug("Power button pressed!")
        if self.coordinator.powerState == _RadioPowerState.POWERED_UP or self.coordinator.powerState == _RadioPowerState.POWERING_DOWN:
            self.coordinator.powerOff()
        else:
            self.coordinator.powerOn()
        