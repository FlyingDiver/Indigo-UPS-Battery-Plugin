#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Copyright (c) 2011, Benjamin Schollnick. All rights reserved.
# http://www.schollnick.net/Wordpress
#
# Copyright (c) 2024, Joe Keenan
#
################################################################################

import subprocess
import time
import logging

current_device_version = 4

################################################################################
class Plugin(indigo.PluginBase):
    ########################################
    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)

        pfmt = logging.Formatter('%(asctime)s.%(msecs)03d\t[%(levelname)8s] %(name)20s.%(funcName)-25s%(msg)s', datefmt='%Y-%m-%d %H:%M:%S')
        self.plugin_file_handler.setFormatter(pfmt)
        self.logLevel = int(pluginPrefs.get("logLevel", logging.INFO))
        self.indigo_log_handler.setLevel(self.logLevel)
        self.plugin_file_handler.setLevel(self.logLevel)
        self.pluginPrefs = pluginPrefs

        self.monitors = []
        self.verify_preference("Timing", 5)
        self.verify_preference("PowerFailureTiming", 1)

    def startup(self):
        self.logger.debug("startup called")

    def shutdown(self):
        self.logger.debug("shutdown called")

    def verify_preference(self, preference_key, default_value):
        if preference_key in self.pluginPrefs:
            return
        else:
            self.pluginPrefs[preference_key] = default_value

    @staticmethod
    def verify_device_properties(dev, property_name, boolean=False, default_value=""):
        newProps = dev.pluginProps  # dev.globalProps[plugin_id]
        if property_name in newProps:
            return
        else:
            if boolean:
                newProps[property_name] = True
            else:
                newProps[property_name] = default_value

            dev.replacePluginPropsOnServer(newProps)

    @staticmethod
    def update_device_property(dev, property_name, new_value):
        newProps = dev.pluginProps
        newProps.update({property_name: new_value})
        dev.replacePluginPropsOnServer(newProps)
        return None

    ########################################

    def deviceStartComm(self, dev):
        self.verify_device_properties(dev, "device_version", boolean=False, default_value="000")
        self.verify_device_properties(dev, "Model", boolean=False, default_value="")
        self.verify_device_properties(dev, "ACPower", boolean=True)
        self.verify_device_properties(dev, "PowerSource", boolean=False, default_value="")

        dv = int(dev.pluginProps["device_version"])
        if current_device_version != dv:
            dev.stateListOrDisplayStateIdChanged()
            self.update_device_property(dev, "device_version", new_value=current_device_version)

        if dev.deviceTypeId == "BatteryMonitor":
            self.monitors.append(dev.id)
            if len(self.monitors) >= 2:
                self.errorLog("Only One Battery & UPS Monitor can be used.")
                self.monitors = self.monitors[0]

    def deviceStopComm(self, dev):
        if dev.deviceTypeId == "BatteryMonitor":
            self.monitors.remove(dev.id)

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        if not userCancelled:
            self.logger.threaddebug(f"closedPrefsConfigUi: valuesDict = {valuesDict}")
            self.logLevel = int(self.pluginPrefs.get("logLevel", logging.INFO))
            self.indigo_log_handler.setLevel(self.logLevel)
            self.logger.debug(f"logLevel = {self.logLevel}")

    def get_battery_status(self):
        proc = subprocess.Popen(['pmset', '-g', 'batt'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = proc.communicate()
        out = out.decode('utf8').split("\n")
        self.logger.debug(f"get_battery_status() = {out}")

        if len(out) == 2:
            return "AC Power - No Battery", "No Battery or UPS", False, 0, 0, 0, 0

        power_status = out[0].split("'")[1]
        data = out[1].split("\t")
        ups_model = data[0]
        data = data[1].split(";")
        percentage = data[0][0:-1]  # data[1][0:percent_locale]
        charging = data[1].find("discharging") == -1
        if not charging:
            ctime = data[2][0:data[2].find(":") + 3].strip()
            c_hours = data[2][0:ctime.find(":") + 1]
            c_min = data[2][ctime.find(":") + 2:ctime.find(":") + 4]
        else:
            ctime = 0
            c_hours = 0
            c_min = 0

        return power_status, ups_model, charging, percentage, ctime, c_hours, c_min

    def runConcurrentThread(self):
        try:
            while True:
                power_status, ups_model, charging, percentage, timestring, hours, c_min = self.get_battery_status()

                if not charging:
                    self.logger.info(f"\tPower Status    - {power_status}")
                    self.logger.info(f"\tUPS Model       - {ups_model}")
                    self.logger.info(f"\tCharging Status - {charging}")
                    self.logger.info(f"\tBattery Charge  - {percentage:>02}")

                if self.monitors == {}:
                    self.logger.info("No Battery & UPS Monitor device defined.")
                else:
                    battery_monitor = indigo.devices[self.monitors[0]]
                    if battery_monitor.states["Model"] != ups_model:
                        battery_monitor.updateStateOnServer("Model", ups_model)

                    if battery_monitor.states["ACPower"] != power_status:
                        battery_monitor.updateStateOnServer("ACPower", power_status)

                    if battery_monitor.states["Charging"] != charging:
                        battery_monitor.updateStateOnServer("Charging", charging)

                    if battery_monitor.states["BatteryLevel"] != percentage:
                        battery_monitor.updateStateOnServer("BatteryLevel", percentage)

                    if battery_monitor.states["BatteryTimeRemaining"] != int(hours) * 60 + int(c_min):
                        battery_monitor.updateStateOnServer("BatteryTimeRemaining", int(hours) * 60 + int(c_min))

                    if battery_monitor.states["PowerSource"] != power_status:
                        battery_monitor.updateStateOnServer("PowerSource", power_status)

                    battery_monitor.updateStateOnServer("TimeDateStamp", time.ctime())

                if charging:
                    self.sleep(int(self.pluginPrefs["Timing"]) * 60)
                else:
                    self.sleep(int(self.pluginPrefs["PowerFailureTiming"]) * 60)

        except self.StopThread:
            self.logger.debug("Stopping Plugin")
