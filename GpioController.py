'''
Created on 07.08.2019

@author: tobias
'''
import RPi.GPIO as GPIO
from enum import Enum
import Configuration
import time
import threading
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
        self.blinkingPeriod_ms = -1
        self.thread = None
        self.blinkTimer = None
        self.intensity = 0
        self.timerIdx = 0
    
    def set(self, state, intensity=100):
        if state != PowerState.OFF and state != PowerState.ON:
            self.ctr.logger.warn("Invalid state: %s" % state)
            return
        
        self.mtx.acquire()
        if self.state == state and (intensity == self.intensity or state == PowerState.OFF):
            self.mtx.release()
            return
        
        self.blinkingPeriod_ms = -1
        if self.blinkTimer:
            self.blinkTimer.cancel()
            
        self.thread = threading.Thread(target=lambda: self._set(state, intensity) or self.mtx.release())
        self.thread.start()
    
    def _set(self, state, intensity=100):
        if intensity < 0 or intensity > 100:
            self.ctr.logger.warning("Invalid intensity: %i" % intensity)
            return
        
        self.state = state
        currentIntensity = self.intensity
        if state == PowerState.ON and intensity > 0:
            self.intensity = intensity
            self.ctr.fade(self.pin, currentIntensity, intensity, self.fadeSteps)
            self.intensity = intensity
        else:
            self.intensity = 0
            self.ctr.fade(self.pin, currentIntensity, 0, self.fadeSteps)
        
    def blink(self, period_ms, intensity=100):
        if period_ms < 0:
            self.ctr.logger.warn("Invalid period: %i" % period_ms)
            return
        
        with self.mtx:
            self.blinkingPeriod_ms = period_ms
            if self.blinkTimer:
                self.blinkTimer.cancel()
            self.timerIdx = self.timerIdx + 1
            self.blinkTimer = threading.Timer(0, function=lambda: self._blink(intensity, self.timerIdx))
            self.blinkTimer.start()
        
    def _blink(self, intensity, idx):
        if idx != self.timerIdx:
            return # safely cancel any old timers that are left over
        with self.mtx:
            if self.blinkingPeriod_ms >= 0:
                self._set(PowerState.ON, intensity)
                self._set(PowerState.OFF, intensity)
                self.blinkTimer = threading.Timer(self.blinkingPeriod_ms/1000, function=lambda: self._blink(intensity, idx))
                self.blinkTimer.start()

class GpioController(object):
    '''
    classdocs
    '''
    
    # todo: pwr button must trigger coordinator action

    def __init__(self, config: Configuration, coordinator):
        '''
        Constructor
        '''
        self.logger = config.logger
        self.logger.info("GpioController initializing...")
        self.gpio_pwr_btn = config.gpio_pwr_btn
        
        self.pin_pwr = config.pin_power
        self.pin_speakers = config.pin_speakers
        
        self.pwm = Adafruit_PCA9685.PCA9685(address=0x40)
        self.pwm.set_pwm_freq(5000)
        for pin in range(0,16):
            self.pwmAsGpio(pin, PowerState.OFF)
    
        self.stereoLight = Light(ctr=self, pin=config.pin_stereo, fadeSteps=5)
        self.needleLight = Light(ctr=self, pin=config.pin_needle, fadeSteps=10)
        self.backLight = Light(ctr=self, pin=config.pin_backlight, fadeSteps=20)
        
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
        
        self.backlightDefaultIntensity = config.backlight_default_brightness
        self.logger.info("GpioController initialized")
        
    def pwmAsGpio(self, pin, state):
        if state is GPIO.HIGH:
            self.pwm.set_pwm(pin, 0, 4095)
        else:
            self.pwm.set_pwm(pin, 0, 0)
            
    def pwmPercent(self, pin, onPercent):
        self.pwm.set_pwm(pin, int(4095-(onPercent/100*4095)), 4095)
        
    def setPowerAndSpeaker(self, state: PowerState):
        if state is PowerState.OFF:
            if self.pin_speakers is not None:
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
            if self.pin_speakers is not None:
                self.pwmAsGpio(self.pin_speakers, GPIO.HIGH)
                self.logger.debug("Speakers on")

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
        
    def setBacklight(self, state = PowerState.ON, intensity = None):
        if self.backLight is None:
            return
        
        if intensity is None:
            intensity = self.backlightDefaultIntensity
                
        if state is not PowerState.ON:
            intensity = 0
            
        self.backLight.set(state, intensity)
        
    def setStereolight(self, state: PowerState, blinking = False):
        if self.stereoLight is None:
            return
        
        if blinking:
            self.stereoLight.blink(0) # blink constantly
        else:
            self.stereoLight.set(state)
            
    def setStereoBlink(self, active=False, pause_s = 0):
        self.logger.debug("StereoLight blink set to %s, pause %i" %(active, pause_s))
        if active:
            self.stereoLight.blink(pause_s*1000)
        else:
            self.stereoLight.set(PowerState.OFF)
        
    def setNeedlelight(self, state: PowerState):
        if self.needleLight is None:
            return
        
        self.needleLight.set(state)
            
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
        