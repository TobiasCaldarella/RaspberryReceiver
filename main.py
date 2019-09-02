'''
Created on 07.08.2019

@author: tobias
'''

import Configuration
import logging
import time
import Needle
import MqttClient
import GpioController
import Coordinator
import TuningWheel
import MpdClient
import IR
from time import sleep
import RPi.GPIO as GPIO
import Bluetooth

GPIO.cleanup()
GPIO.setmode(GPIO.BCM)


if __name__ == '__main__':
    config = Configuration.Configuration()
    loggingFormat = '%(asctime)s %(thread)d %(message)s'
    logging.basicConfig(format=loggingFormat, filename=config.logfile, level=config.loglevel)
    logger = logging.getLogger()
    logger.debug("RaspberryReceiver version %s started." % (config.version))
    config.logger = logger
    
    coordinator = Coordinator.Coordinator(logger, config)
    if config.gpio_mag_right is not None and config.gpio_mag_left is not None:
        tuning_wheel = TuningWheel.TuningWheel(config, coordinator)
    else:
        logger.info("Not initializing TuningWheel since gpio_mag_right and/or gpio_mag_left are not set in configuration")
    
    ir = IR.IR(config, coordinator)
    
    if config.mqtt_server is not None and config.mqtt_port is not None and config.mqtt_base_topic is not None:
        mqttClient = MqttClient.MqttClient(config, coordinator)
    else:
        logger.info("MqttClient nont initialized since mqtt_server, mqtt_port and/or mqtt_base_topic are not set in configuration")
    
    pwrcnt = GpioController.GpioController(config, coordinator)
    mpdClient = MpdClient.MpdClient(config, coordinator)
    needle = Needle.Needle(config, coordinator)
    bluetooth = Bluetooth.Bluetooth(config, coordinator)
    
    coordinator.initialize()
    
    while True:
        logger.debug("-MARK-")
        sleep(10)
    
    