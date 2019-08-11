'''
Created on 07.08.2019

@author: tobias
'''

class Configuration(object):
    '''
    classdocs
    '''
    version = '0.1'

    def __init__(self):
        # Logging
        self.logfile = '/tmp/raspberryReceiver.log'
        self.loglevel = 'DEBUG'
        self.logger = None
        
        # MQTT
        self.mqtt_server = '192.168.1.3'
        self.mqtt_port = 1883
        self.mqtt_user = 'zigbee'
        self.mqtt_pass = 'zigbee'
        self.mqtt_base_topic = 'nikko7070'
        
        # GPIOs light
        self.gpio_power = 4
        self.gpio_needle = 24
        self.gpio_backlight = 18
        self.gpio_stereo = 23
        
        # GPIOs tuning wheel mag sensors
        self.gpio_mag_left = 20
        self.gpio_mag_right = 21
        self.wheel_button = 25

        # GPIOs switches and buttons
        self.gpio_pwr_btn = 15
        self.gpio_ukw_mute = 16
        self.gpio_speakers = 12
        
        # MPD stuff
        self.mpd_radio_playlist = "http://local_pub.openhabianpi/radio.m3u"
        
        # Needle mover
        self.gpio_needle_a = 19
        self.gpio_needle_b = 13
        self.gpio_needle_c = 6
        self.gpio_needle_d = 5
        self.needle_steps = 1000
        self.needle_left_margin = 150
        self.needle_sleep_time = 0.002
        