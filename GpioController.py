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
        self.intensity = 100
        self.timerIdx = 0
    
    def set(self, state=None, intensity=None):        
        self.mtx.acquire()
        if intensity is None:
            intensity = self.intensity
            
        if self.state == state and intensity == self.intensity and self.blinkingPeriod_ms == -1:
            self.mtx.release()
            return
        
        if state is None:
            state = self.state
        else:
            self.blinkingPeriod_ms = -1 # if a state is set, cancel blinking
            if self.blinkTimer:
                self.blinkTimer.cancel()            
            
        self.thread = threading.Thread(target=lambda: self._set(state, intensity) or self.mtx.release())
        self.thread.start()
    
    def _set(self, state, intensity):
        if intensity is None:
            intensity = self.intensity
        if intensity < 0 or intensity > 100:
            self.ctr.logger.warning("Invalid intensity: %i" % intensity)
            return
        self.ctr.logger.debug("Setting state %s intensity %i" % (state, intensity))
        
        currentIntensity = self.intensity
        if self.state == PowerState.OFF:
            currentIntensity = 0
        self.state = state
        self.intensity = intensity
        if state == PowerState.ON:
            self.ctr.fade(self.pin, currentIntensity, intensity, self.fadeSteps)
        else:
            #self.intensity = 0
            self.ctr.fade(self.pin, currentIntensity, 0, self.fadeSteps)
        
    def blink(self, period_ms, intensity=None):
        if period_ms < 0:
            self.ctr.logger.warn("Invalid period: %i" % period_ms)
            return
        
        with self.mtx:
            if intensity is not None:
                self.intensity = intensity
            #if intensity is None:
            #    intensity = self.intensity
            self.blinkingPeriod_ms = period_ms
            if self.blinkTimer:
                self.blinkTimer.cancel()
            self.timerIdx = self.timerIdx + 1
            self.blinkTimer = threading.Timer(0, function=lambda: self._blink(intensity=None, idx=self.timerIdx))
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
        self.gpio_bluetooth_enabled = config.gpio_bluetooth_enabled
        
        self.pin_pwr = config.pin_power
        self.pin_speakers = config.pin_speakers
        
        self.pwmMtx = threading.Lock()
        self.pwm = Adafruit_PCA9685.PCA9685(address=0x40)
        self.pwm.set_pwm_freq(100)
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
        
        for pin in [ self.gpio_pwr_btn, self.gpio_bluetooth_enabled ]:
            if pin is not None:
                GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.add_event_detect(self.gpio_bluetooth_enabled, GPIO.BOTH, callback=self.do_bluetooth_switch, bouncetime=30)    
        
        self.backlightDefaultIntensity = config.backlight_default_brightness
        self.logger.info("GpioController initialized")
        
    def pwmAsGpio(self, pin, state):
        with self.pwmMtx:
            if state is GPIO.HIGH:
                self.pwm.set_pwm(pin, 0, 4095)
            else:
                self.pwm.set_pwm(pin, 0, 0)
            
    def pwmPercent(self, pin, onPercent):
        with self.pwmMtx:
            self.pwm.set_pwm(pin, int(4095-(onPercent/100*4095)), 4095)
        
    def _powerUpSpeakers(self):
        self.pwmAsGpio(self.pin_speakers, GPIO.HIGH)
        self.logger.info("Speakers on")
        
    def setPowerAndSpeaker(self, state: PowerState):
        if state is PowerState.OFF:
            if self.pin_speakers is not None:
                self.pwmAsGpio(self.pin_speakers, GPIO.LOW)
                self.logger.debug("Speakers off")
                time.sleep(0.5)
            self.pwmAsGpio(self.pin_pwr, GPIO.LOW)
            self.logger.info("Powered down")
            time.sleep(0.5)
        else:
            if self.pin_speakers is not None:
                self.pwmAsGpio(self.pin_speakers, GPIO.LOW)
                time.sleep(0.5)
            self.pwmAsGpio(self.pin_pwr, GPIO.HIGH)
            self.logger.info("Amp Powered up")
            if self.pin_speakers is not None:
                threading.Timer(interval=2.0, function=self._powerUpSpeakers).start()

    def fade(self, pin, current, target, steps):
        self.logger.debug("pin %i current %i target %i" % (pin,current,target))
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
        if self.backLight is None:
            return
        self.backLight.set(state, intensity)
        
    def setStereolight(self, state = None, blinking = False, intensity = None):
        if self.stereoLight is None:
            return
        
        if blinking:
            self.stereoLight.blink(0, intensity) # blink constantly
        else:
            self.stereoLight.set(state, intensity)
            
    def setStereoBlink(self, active=False, pause_s = 0, intensity = None):
        self.logger.debug("StereoLight blink set to %s, pause %i" %(active, pause_s))
        if active:
            self.stereoLight.blink(pause_s*1000, intensity)
        else:
            self.stereoLight.set(PowerState.OFF, intensity)
        
    def setNeedlelight(self, state = None, intensity = None):
        if self.needleLight is None:
            return
        self.needleLight.set(state, intensity)
        
    def setNeedleLightBlink(self, active=False, pause_s = 0, intensity = None):
        self.logger.debug("StereoLight blink set to %s, pause %i" %(active, pause_s))
        if active:
            self.needleLight.blink(pause_s*1000, intensity)
        else:
            self.needleLight.set(PowerState.OFF, intensity)
            
    def enable_power_button(self):
        self.logger.debug("Power button enabled")
        GPIO.add_event_detect(self.gpio_pwr_btn, GPIO.FALLING, callback=self.do_power_button, bouncetime=300)    
    
    def disable_power_button(self):
        self.logger.debug("Power button disabled")
        GPIO.remove_event_detect(self.gpio_pwr_btn)
        
    def do_bluetooth_switch(self, ch):
        state = GPIO.input(self.gpio_bluetooth_enabled)
        time.sleep(0.05)
        if GPIO.input(self.gpio_bluetooth_enabled) != state:
            self.logger.debug("Spurious bt switch interrupt, ignored.")
            return
        time.sleep(0.05)
        if GPIO.input(self.gpio_bluetooth_enabled) != state:
            self.logger.debug("Spurious bt switch interrupt, ignored.")
            return
        
        self.logger.info("Bluetooth switch = %s" % state)
        if state == GPIO.HIGH:
            self.coordinator.bluetoothControl(False)
        else:
            self.coordinator.bluetoothControl(True)
        
        
    def do_power_button(self, ch):
        if GPIO.input(self.gpio_pwr_btn) != GPIO.LOW:
            self.logger.debug("Spurious power button interrupt, ignored.")
            return
        self.logger.info("Power button pressed!")
        if self.coordinator.powerState == _RadioPowerState.POWERED_UP or self.coordinator.powerState == _RadioPowerState.POWERING_DOWN:
            self.coordinator.powerOff()
        else:
            self.coordinator.powerOn()
        