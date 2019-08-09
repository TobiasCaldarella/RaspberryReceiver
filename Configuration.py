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
        self.gpio_power = 1
        self.gpio_needle = 2
        self.gpio_backlight = 3
        self.gpio_stereo = 4
        
        # GPIOs tuning wheel mag sensors
        self.gpio_mag_left = 5
        self.gpio_mag_right = 6

        # GPIOs switches and buttons
        self.gpio_pwr_btn = 7
        self.gpio_ukw_mute = 8
        self.gpio_speakers = 9
        
        # MPD stuff
        self.mpd_radio_playlist = "radio.m3u"
        