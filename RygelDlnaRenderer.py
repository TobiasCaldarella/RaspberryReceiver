'''
Created on 14.10.2020

@author: tobias
'''
import subprocess

class RygelDlnaRenderer(object):
    '''
    classdocs
    '''

    def __init__(self, config, coordinator):
        self.logger = config.logger
        self.coordinator = coordinator
        self.rygel = None
        coordinator.dlnaRenderer = self
        
    def start(self):
        if self.rygel is not None:
            self.logger.error("RygelDlnaRenderer: Rygel already/still running!")
            return False
        self.rygel = subprocess.Popen(['rygel'])
    
    def stop(self):
        if self.rygel is None:
            return True
        self.rygel.terminate()
        try:
            self.rygel.wait(5)
        except:
            self.logger.error("RygelDlnaRenderer: Rygel did not terminate. Kill it.")
            self.rygel.kill()
            self.rygel.wait(5)
        self.rygel = None
        