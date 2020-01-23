'''
Created on 07.08.2019

@author: tobias
'''

from enum import Enum
class _RadioState(Enum):
    STOPPED = 0
    PLAYING = 1
    BLUETOOTH = 2
    
class _RadioPowerState(Enum):
    POWERED_DOWN = 0
    POWERING_UP = 1
    POWERED_UP = 2
    POWERING_DOWN = 3

class Configuration(object):
    '''
    classdocs
    '''
    version = '0.1'

    def __init__(self):
        # Logging
        self.logfile = '/var/log/raspberryReceiver.log'
        self.loglevel = 'INFO'
        self.logger = None
        
        # MQTT
        self.mqtt_server = '192.168.1.3'
        self.mqtt_port = 1883
        self.mqtt_user = 'zigbee'
        self.mqtt_pass = 'zigbee'
        self.mqtt_base_topic = 'nikko7070'
        self.mqtt_reconnect_period_s = 30
        
        # PWM board
        self.pin_power = 5
        self.pin_needle = 6
        self.pin_backlight = 0
        self.pin_stereo = 7
        self.pin_speakers = 4
        
        # GPIOs tuning wheel mag sensors
        self.gpio_mag_left = 24
        self.gpio_mag_right = 4
        self.wheel_button = 14

        # GPIOs switches and buttons
        self.gpio_pwr_btn = 9
        self.gpio_ukw_mute = 16
        
        # MPD stuff
        self.mpd_radio_playlist = "http://local_pub.openhabianpi/radio.m3u"
        self.mpd_local_playlist = "/var/lib/mpd/playlists/radio.m3u"
        self.mpd_playlist_name = "radio"
        # Needle mover
        self.gpio_needle_a = 22
        self.gpio_needle_b = 17
        self.gpio_needle_c = 23
        self.gpio_needle_d = 27
        self.needle_steps = 950
        self.needle_left_margin = 150
        self.needle_sleep_time = 0.002
        
        # text to speech options
        self.tts_api_key = '88ecced13cfe4f2b938c13e5dfdf1575'
        self.tts_cache_dir = '/var/cache/RaspberryReceiver/tts'
        
        # misc options
        self.backlight_default_brightness = 100
        self.backlight_sleep_brightness = 10
        self.stereo_default_brightness= 100
        