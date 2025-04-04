# Copyright 2021-2024 Foundries.io
#
# SPDX-License-Identifier: BSD-3-Clause

import json
import celery
import os
import yaml
from datetime import datetime, timedelta
from django.conf import settings
from django.test import TestCase
from git import Repo
from unittest.mock import call, patch, Mock, MagicMock, PropertyMock

from conductor.core.models import (
    Project,
    Build,
    BuildTag,
    Run,
    LAVABackend,
    SQUADBackend,
    LAVADeviceType,
    LAVADevice,
    LAVAJob,
    DEFAULT_TIMEOUT
)
from conductor.testplan.models import (
    TestPlan,
    TestJob
)
from conductor.core.tasks import (
    create_build_run,
    create_project_repository,
    create_upgrade_commit,
    update_build_reason,
    update_build_commit_id,
    tag_build_runs,
    process_testjob_notification,
    schedule_lmp_pr_tests,
    schedule_static_delta,
    create_static_delta_build,
    poll_static_delta_build,
    fetch_lmp_code_review,
    schedule_project_test_round
)


def assert_not_called_with(self, *args, **kwargs):
    try:
        self.assert_called_with(*args, **kwargs)
    except AssertionError:
        return
    raise AssertionError('Expected %s to not have been called.' % self._format_mock_call_signature(args, kwargs))

Mock.assert_not_called_with = assert_not_called_with


LMP_BUILD_JSON = """
{
      "build_id": 2225,
      "completed": "2023-06-01T16:17:05+00:00",
      "created": "2023-05-31T22:27:50+00:00",
      "reason": "GitHub PR(337): pull_request, https://github.com/foundriesio/lmp-manifest/pull/337",
      "runs": [
        {
          "completed": "2023-05-31T23:04:44+00:00",
          "created": "2023-05-31T22:30:58+00:00",
          "host_tag": "amd64-partner-gcp-nocache",
          "log_url": "https://api.foundries.io/projects/lmp/builds/2225/runs/build-imx8mm-lpddr4-evk/console.log",
          "name": "build-imx8mmevk",
          "status": "PASSED",
          "url": "https://api.foundries.io/projects/lmp/builds/2225/runs/build-imx8mm-lpddr4-evk/",
          "web_url": "https://ci.foundries.io/projects/lmp/builds/2225/build-imx8mm-lpddr4-evk/"
        }
      ], 
      "runs_url": "https://api.foundries.io/projects/lmp/builds/2225/runs/", 
      "status": "PASSED", 
      "status_events": [
        {
          "status": "QUEUED", 
          "time": "2023-05-31T22:27:50+00:00"
        }, 
        {
          "status": "RUNNING", 
          "time": "2023-05-31T22:29:47+00:00"
        }, 
        {
          "status": "FAILED", 
          "time": "2023-06-01T11:06:21+00:00"
        }, 
        {
          "status": "RUNNING", 
          "time": "2023-06-01T14:06:24+00:00"
        }, 
        {
          "status": "PASSED", 
          "time": "2023-06-01T16:17:05+00:00"
        }
      ], 
      "trigger_name": "Code Review", 
      "url": "https://api.foundries.io/projects/lmp/builds/2225/", 
      "web_url": "https://ci.foundries.io/projects/lmp/builds/2225"
    }
"""


DEVICE_DETAILS = """
{
    "device_type": "bcm2711-rpi-4-b",
    "device_version": null,
    "physical_owner": null,
    "physical_group": null,
    "description": "Created automatically by LAVA.",
    "tags": [],
    "state": "Idle",
    "health": "Unknown",
    "last_health_report_job": 1,
    "worker_host": "rpi-01-worker",
    "is_synced": true
}
"""

DEVICE_DICT = """# in milliseconds
character_delays:
      boot: 5
      test: 5
constants:

  # POSIX os (not AOSP)
  posix:
    lava_test_sh_cmd: /bin/sh
    lava_test_results_dir: /lava-%s
    lava_test_shell_file: ~/.bashrc

  # bootloader specific
  barebox:
    interrupt-prompt: 'Hit m for menu or any other key to stop autoboot'
    interrupt-character: '
'
    final-message: 'Starting kernel'
    error-messages:
      - '### ERROR ### Please RESET the board ###'
      - 'ERROR: .*'
      - '.*: Out of memory'
  u-boot:
    interrupt-prompt: 'Hit any key to stop autoboot'
    interrupt-character: ' '
    interrupt_ctrl_list: []
    interrupt-newline: True
    final-message: 'Starting kernel'
    error-messages:
      - 'Resetting CPU'
      - 'Must RESET board to recover'
      - 'TIMEOUT'
      - 'Retry count exceeded'
      - 'Retry time exceeded; starting again'
      - 'ERROR: The remote end did not respond in time.'
      - 'File not found'
      - 'Bad Linux ARM64 Image magic!'
      - 'Wrong Ramdisk Image Format'
      - 'Ramdisk image is corrupt or invalid'
      - 'ERROR: Failed to allocate'
      - 'TFTP error: trying to overwrite reserved memory'
      - 'Invalid partition'
    dfu-download: 'DOWNLOAD \.\.\. OK\r\nCtrl\+C to exit \.\.\.'
  grub:
    interrupt-prompt: 'for a command-line'
    interrupt-character: 'c'
    interrupt-newline: False
    error-messages:
      - "error: missing (.*) symbol."
  grub-efi:
    interrupt-prompt: 'for a command-line'
    interrupt-character: 'c'
    error-messages:
      - 'Undefined OpCode Exception PC at'
      - 'Synchronous Exception at'
      - "error: missing (.*) symbol."
  ipxe:
    interrupt-prompt: 'Press Ctrl-B for the iPXE command line'
    interrupt_ctrl_list: ['b']
    error-messages:
      - 'No configuration methods succeeded'
      - 'Connection timed out'

  # OS shutdown message
  # Override: set as the shutdown-message parameter of an Action.
  # SHUTDOWN_MESSAGE
  shutdown-message: 'The system is going down for reboot NOW'

  # Kernel starting message
  kernel-start-message: 'Linux version [0-9]'

  # Default shell prompt for AutoLogin
  # DEFAULT_SHELL_PROMPT
  default-shell-prompt: 'lava-test: # '

  # pexpect.spawn maxread
  # SPAWN_MAXREAD - in bytes, quoted as a string
  # 1 to turn off buffering, pexpect default is 2000
  # maximum may be limited by platform issues to 4092
  # avoid setting searchwindowsize:
  # Data before searchwindowsize point is preserved, but not searched.
  spawn_maxread: '4092'
commands:
    connections:
        uart0:
            connect: telnet ser2net 7002
            tags:
            - primary
            - telnet
    hard_reset: /usr/local/bin/eth008_control -a 192.168.0.21 -r 1 -s offon -d 5
    power_off: ['/usr/local/bin/eth008_control -a 192.168.0.21 -r 1 -s off', '/usr/local/bin/eth008_control -a 192.168.0.21 -r 2 -s off', '/usr/local/bin/eth008_control -a 192.168.0.21 -r 3 -s off']
    power_on: /usr/local/bin/eth008_control -r 1 -s on
device_info: [{'board_id': Undefined}]
parameters:
  # interfaces or device_ip or device_mac

  pass: # sata_uuid_sd_uuid_usb_uuid

  image:
    kernel: '0x40480000'
    ramdisk: '0x44000000'
    dtb: '0x43000000'
    tee: '0x83000000'
  booti:
    kernel: '0x40480000'
    ramdisk: '0x44000000'
    dtb: '0x43000000'
    tee: '0x83000000'
  uimage:
    kernel: '0x40480000'
    ramdisk: '0x44000000'
    dtb: '0x43000000'
    tee: '0x83000000'
  bootm:
    kernel: '0x40480000'
    ramdisk: '0x44000000'
    dtb: '0x43000000'
    tee: '0x83000000'
  zimage:
    kernel: '0x40480000'
    ramdisk: '0x44000000'
    dtb: '0x43000000'
    tee: '0x83000000'
  bootz:
    kernel: '0x40480000'
    ramdisk: '0x44000000'
    dtb: '0x43000000'
    tee: '0x83000000'

        
adb_serial_number: "0000000000"
fastboot_serial_number: "0000000000"
fastboot_options: ['-i', '0x0525']
# This attribute identifies whether a device should get into fastboot mode by
# interrupting uboot and issuing commands at the bootloader prompt.
fastboot_via_uboot: True

actions:
  deploy:
    parameters:
      add_header: u-boot
      mkimage_arch: arm64 # string to pass to mkimage -A when adding UBoot headers
      append_dtb: False
      use_xip: False
    connections:
      lxc:
      fastboot:
      serial:
    methods:
      flasher:
        commands: ['/usr/local/bin/eth008_control -a 192.168.0.21 -r 1 -s off', '/usr/local/bin/eth008_control -a 192.168.0.21 -r 2 -s on', '/usr/local/bin/eth008_control -a 192.168.0.21 -r 3 -s on', '/usr/local/bin/eth008_control -a 192.168.0.21 -r 1 -s on', 'sleep 1', 'flash-imx8.sh -i "{IMAGE}" -b "{BOOTLOADER}" -u "{UBOOT}" -s "{SITIMG}" -p "1:2"', '/usr/local/bin/eth008_control -a 192.168.0.21 -r 1 -s off', '/usr/local/bin/eth008_control -a 192.168.0.21 -r 2 -s off', '/usr/local/bin/eth008_control -a 192.168.0.21 -r 3 -s off']
      image:
      lxc:
      overlay:
      usb:
      tftp:
      nbd:
      ssh:
        options:
          - '-o'
          - 'Compression=yes'
          - '-o'
          - 'PasswordAuthentication=no'
          - '-o'
          - 'LogLevel=FATAL'

        host: ""
        port: 22
        user: "root"
        identity_file: "dynamic_vm_keys/lava"
      fastboot:
      u-boot:
        parameters:
          bootloader_prompt: ""
          interrupt_prompt: ""
          interrupt_char: ""
          fastboot:
            commands:
              - fastboot 0

  boot:
    connections:
      lxc:
      fastboot:
      serial:
    methods:
      minimal:
      ssh:
      dfu:
        implementation: u-boot
        reset_works: False
        parameters:
          enter-commands:
          command: dfu-util
      fastboot: ['reboot']
      u-boot:
        parameters:
          bootloader_prompt: =>
          interrupt_prompt: Hit any key to stop autoboot
          interrupt_char: ""
          needs_interrupt: True


        # method specific stanza
        ums:
          commands:
          - "ums 0 mmc 1"
        nfs:
          commands:
          - "setenv autoload no"
          - "setenv initrd_high 0xffffffff"
          - "setenv fdt_high 0xffffffff"
          - "dhcp"
          - "setenv serverip {SERVER_IP}"
          - "tftp {KERNEL_ADDR} {KERNEL}"
          - "tftp {RAMDISK_ADDR} {RAMDISK}"
          - "tftp {TEE_ADDR} {TEE}"
          - "setenv initrd_size ${filesize}"
          - "tftp {DTB_ADDR} {DTB}"
          # Always quote the entire string if the command includes a colon to support correct YAML.
          - "setenv bootargs 'console=ttymxc1,115200 earlycon=ec_imx6q,0x30890000,115200n8 root=/dev/nfs rw nfsroot={NFS_SERVER_IP}:{NFSROOTFS},tcp,hard,v3  ip=dhcp'"
          - "{BOOTX}"
        nbd:
          commands:
          - "setenv autoload no"
          - "setenv initrd_high 0xffffffff"
          - "setenv fdt_high 0xffffffff"
          - "dhcp"
          - "setenv serverip {SERVER_IP}"
          - "tftp {KERNEL_ADDR} {KERNEL}"
          - "tftp {RAMDISK_ADDR} {RAMDISK}"
          - "tftp {TEE_ADDR} {TEE}"
          - "setenv initrd_size ${filesize}"
          - "tftp {DTB_ADDR} {DTB}"
          # Always quote the entire string if the command includes a colon to support correct YAML.
          - "setenv bootargs 'console=ttymxc1,115200 earlycon=ec_imx6q,0x30890000,115200n8 rw nbd.server={NBDSERVERIP} nbd.port={NBDSERVERPORT} root=/dev/ram0 ramdisk_size=16384 rootdelay=7   ip=dhcp verbose earlyprintk systemd.log_color=false ${extraargs} rw'"
          - "{BOOTX}"
        ramdisk:
          commands:
          - "setenv autoload no"
          - "setenv initrd_high 0xffffffff"
          - "setenv fdt_high 0xffffffff"
          - "dhcp"
          - "setenv serverip {SERVER_IP}"
          - "tftp {KERNEL_ADDR} {KERNEL}"
          - "tftp {RAMDISK_ADDR} {RAMDISK}"
          - "tftp {TEE_ADDR} {TEE}"
          - "setenv initrd_size ${filesize}"
          - "tftp {DTB_ADDR} {DTB}"
          - "setenv bootargs 'console=ttymxc1,115200 earlycon=ec_imx6q,0x30890000,115200n8 root=/dev/ram0  ip=dhcp'"
          - "{BOOTX}"
        usb:
          commands:
          - "usb start"
          - "setenv autoload no"
          - "load usb :{ROOT_PART} {KERNEL_ADDR} {KERNEL}"
          - "load usb :{ROOT_PART} {RAMDISK_ADDR} {RAMDISK}"
          - "setenv initrd_size ${filesize}"
          - "load usb :{ROOT_PART} {DTB_ADDR} {DTB}"
          - "console=ttymxc1,115200 earlycon=ec_imx6q,0x30890000,115200n8 root={ROOT}  ip=dhcp"
          - "{BOOTX}"
        sata:
          commands:
          - "scsi scan"
          - "setenv autoload no"
          - "load scsi {ROOT_PART} {KERNEL_ADDR} {KERNEL}"
          - "load scsi {ROOT_PART} {RAMDISK_ADDR} {RAMDISK}; setenv initrd_size ${filesize}"
          - "load scsi {ROOT_PART} {DTB_ADDR} {DTB}"
          - "setenv bootargs 'console=ttymxc1,115200 earlycon=ec_imx6q,0x30890000,115200n8 root={ROOT}  ip=dhcp'"
          - "{BOOTX}"
      uuu:
        options:
          usb_otg_path: ""
          corrupt_boot_media_command: 
          docker_image: ""
          remote_options: ""


timeouts:
  actions:
    apply-overlay-image:
      minutes: 2
    dd-image:
      minutes: 10
    download-retry:
      minutes: 5
    http-download:
      minutes: 5
    lava-test-shell:
      minutes: 3
    nfs-deploy:
      minutes: 10
    power-off:
      seconds: 10
    bootloader-commands:
      minutes: 3
    bootloader-interrupt:
      seconds: 30
    u-boot-interrupt:
      seconds: 30
    umount-retry:
      seconds: 45
    auto-login-action:
      minutes: 2
    bootloader-action:
      minutes: 3
    uboot-action:
      minutes: 3
    uboot-commands:
      minutes: 3
    bootloader-retry:
      minutes: 3
    boot-qemu-image:
      minutes: 2
    boot-image-retry:
      minutes: 2
    flash-uboot-ums:
      minutes: 20
    musca-deploy:
      minutes: 3
    musca-boot:
      minutes: 1
    unmount-musca-usbmsd:
      seconds: 30
    pdu-reboot:
      seconds: 30
    reset-device:
      seconds: 30
  connections:
    dd-image:
      minutes: 10
    uboot-commands:
      seconds: 30
    bootloader-commands:
      seconds: 30
    auto-login-action:
      minutes: 2
    bootloader-interrupt:
      seconds: 30
    u-boot-interrupt:
      seconds: 30
    lava-test-shell:
      seconds: 10
    lava-docker-test-shell:
      seconds: 10
"""

TARGET_DICT={"aktualizr-toml": "[logger]\nloglevel = 2\n\n[p11]\nmodule = \"\"\npass = \"\"\nuptane_key_id = \"\"\ntls_ca_id = \"\"\ntls_pkey_id = \"\"\ntls_clientcert_id = \"\"\n\n[tls]\nserver = \"https://ota-lite.foundries.io:8443\"\nserver_url_path = \"\"\nca_source = \"file\"\npkey_source = \"file\"\ncert_source = \"file\"\n\n[provision]\nserver = \"https://ota-lite.foundries.io:8443\"\np12_password = \"\"\nexpiry_days = \"36000\"\nprovision_path = \"\"\ndevice_id = \"\"\nprimary_ecu_serial = \"\"\nprimary_ecu_hardware_id = \"imx8mmevk\"\necu_registration_endpoint = \"https://ota-lite.foundries.io:8443/director/ecus\"\nmode = \"DeviceCred\"\n\n[uptane]\npolling_sec = 300\ndirector_server = \"https://ota-lite.foundries.io:8443/director\"\nrepo_server = \"https://ota-lite.foundries.io:8443/repo\"\nkey_source = \"file\"\nkey_type = \"RSA2048\"\nforce_install_completion = False\nsecondary_config_file = \"\"\nsecondary_preinstall_wait_sec = 600\n\n[pacman]\ntype = \"ostree+compose_apps\"\nos = \"\"\nsysroot = \"\"\nostree_server = \"https://ota-lite.foundries.io:8443/treehub\"\nimages_path = \"/var/sota/images\"\npackages_file = \"/usr/package.manifest\"\nfake_need_reboot = False\ncallback_program = \"/var/sota/aklite-callback.sh\"\ncompose_apps_root = \"/var/sota/compose-apps\"\ntags = \"master\"\n\n[storage]\ntype = \"sqlite\"\npath = \"/var/sota/\"\nsqldb_path = \"sql.db\"\nuptane_metadata_path = \"/var/sota/metadata\"\nuptane_private_key_path = \"ecukey.der\"\nuptane_public_key_path = \"ecukey.pub\"\ntls_cacert_path = \"root.crt\"\ntls_pkey_path = \"pkey.pem\"\ntls_clientcert_path = \"client.pem\"\n\n[import]\nbase_path = \"/var/sota/import\"\nuptane_private_key_path = \"\"\nuptane_public_key_path = \"\"\ntls_cacert_path = \"/var/sota/root.crt\"\ntls_pkey_path = \"/var/sota/pkey.pem\"\ntls_clientcert_path = \"/var/sota/client.pem\"\n\n[telemetry]\nreport_network = True\nreport_config = True\n\n[bootloader]\nrollback_mode = \"uboot_masked\"\nreboot_sentinel_dir = \"/var/run/aktualizr-session\"\nreboot_sentinel_name = \"need_reboot\"\nreboot_command = \"/sbin/reboot\"\n\n", "hardware-info": {"capabilities": {"cp15_barrier": True, "setend": True, "smp": "Symmetric Multi-Processing", "swp": True, "tagged_addr_disabled": True}, "children": [{"children": [{"businfo": "cpu@0", "capabilities": {"aes": "AES instructions", "asimd": "Advanced SIMD", "cpufreq": "CPU Frequency scaling", "cpuid": True, "crc32": "CRC extension", "evtstrm": "Event stream", "fp": "Floating point instructions", "pmull": "PMULL instruction", "sha1": "SHA1 instructions", "sha2": "SHA2 instructions"}, "capacity": 1800000000, "claimed": True, "class": "processor", "description": "CPU", "id": "cpu:0", "physid": "0", "product": "cpu", "size": 1800000000, "units": "Hz"}, {"businfo": "cpu@1", "capabilities": {"aes": "AES instructions", "asimd": "Advanced SIMD", "cpufreq": "CPU Frequency scaling", "cpuid": True, "crc32": "CRC extension", "evtstrm": "Event stream", "fp": "Floating point instructions", "pmull": "PMULL instruction", "sha1": "SHA1 instructions", "sha2": "SHA2 instructions"}, "capacity": 1800000000, "claimed": True, "class": "processor", "description": "CPU", "id": "cpu:1", "physid": "1", "product": "cpu", "size": 1800000000, "units": "Hz"}, {"businfo": "cpu@2", "capabilities": {"aes": "AES instructions", "asimd": "Advanced SIMD", "cpufreq": "CPU Frequency scaling", "cpuid": True, "crc32": "CRC extension", "evtstrm": "Event stream", "fp": "Floating point instructions", "pmull": "PMULL instruction", "sha1": "SHA1 instructions", "sha2": "SHA2 instructions"}, "capacity": 1800000000, "claimed": True, "class": "processor", "description": "CPU", "id": "cpu:2", "physid": "2", "product": "cpu", "size": 1800000000, "units": "Hz"}, {"businfo": "cpu@3", "capabilities": {"aes": "AES instructions", "asimd": "Advanced SIMD", "cpufreq": "CPU Frequency scaling", "cpuid": True, "crc32": "CRC extension", "evtstrm": "Event stream", "fp": "Floating point instructions", "pmull": "PMULL instruction", "sha1": "SHA1 instructions", "sha2": "SHA2 instructions"}, "capacity": 1800000000, "claimed": True, "class": "processor", "description": "CPU", "id": "cpu:3", "physid": "3", "product": "cpu", "size": 1800000000, "units": "Hz"}, {"businfo": "cpu@4", "claimed": True, "class": "processor", "description": "CPU", "disabled": True, "id": "cpu:4", "physid": "4", "product": "idle-states"}, {"businfo": "cpu@5", "claimed": True, "class": "processor", "description": "CPU", "disabled": True, "id": "cpu:5", "physid": "5", "product": "l2-cache0"}, {"claimed": True, "class": "memory", "description": "System memory", "id": "memory", "physid": "6", "size": 2045693952, "units": "bytes"}], "claimed": True, "class": "bus", "description": "Motherboard", "id": "core", "physid": "0"}, {"children": [{"businfo": "mmc@0:0001:1", "capabilities": {"sdio": True}, "claimed": True, "class": "generic", "description": "SDIO Device", "id": "device", "logicalname": "mmc0:0001:1", "physid": "0", "serial": "0"}], "claimed": True, "class": "bus", "description": "MMC Host", "id": "mmc0", "logicalname": "mmc0", "physid": "1"}, {"claimed": True, "class": "bus", "description": "MMC Host", "id": "mmc1", "logicalname": "mmc1", "physid": "2"}, {"children": [{"businfo": "mmc@2:0001", "capabilities": {"mmc": True}, "children": [{"claimed": True, "class": "generic", "id": "interface:0", "logicalname": "/dev/mmcblk2rpmb", "physid": "1"}, {"capabilities": {"partitioned": "Partitioned disk", "partitioned:dos": "MS-DOS partition table"}, "children": [{"capabilities": {"bootable": "Bootable partition (active)", "fat": "Windows FAT", "initialized": "initialized volume", "primary": "Primary partition"}, "capacity": 87240704, "class": "volume", "configuration": {"FATs": "2", "filesystem": "fat", "label": "boot"}, "description": "Windows FAT volume", "id": "volume:0", "physid": "1", "serial": "5b3c-9223", "size": 87238656, "vendor": "mkfs.fat", "version": "FAT16"}, {"capabilities": {"dir_nlink": "directories with 65000+ subdirs", "ext2": "EXT2/EXT3", "ext4": True, "extended_attributes": "Extended Attributes", "extents": "extent-based allocation", "huge_files": "16TB+ files", "initialized": "initialized volume", "journaled": True, "large_files": "4GB+ files", "primary": "Primary partition", "recover": "needs recovery"}, "capacity": 15665725440, "claimed": True, "class": "volume", "configuration": {"created": "2021-01-28 11:27:02", "filesystem": "ext4", "label": "otaroot", "lastmountpoint": "/rootfs", "modified": "2021-01-29 15:17:42", "mount.fstype": "ext4", "mount.options": "rw,relatime", "mounted": "2021-01-29 15:17:42", "state": "mounted"}, "description": "EXT4 volume", "dev": "179:2", "id": "volume:1", "logicalname": ["/dev/mmcblk2p2", "/sysroot", "/", "/boot", "/usr", "/var"], "physid": "2", "serial": "c6183363-9b9b-498c-b7d8-eb849672408f", "size": 15665725440, "vendor": "Linux", "version": "1.0"}], "claimed": True, "class": "generic", "configuration": {"logicalsectorsize": "512", "sectorsize": "512", "signature": "f24cd3de"}, "id": "interface:1", "logicalname": "/dev/mmcblk2", "physid": "2", "size": 15758000128}], "claimed": True, "class": "generic", "date": "08/2020", "description": "SD/MMC Device", "id": "device", "physid": "1", "product": "DG4016", "serial": "448766742", "vendor": "Unknown (69)"}], "claimed": True, "class": "bus", "description": "MMC Host", "id": "mmc2", "logicalname": "mmc2", "physid": "3"}, {"claimed": True, "class": "multimedia", "description": "imxspdif", "id": "sound:0", "logicalname": ["card0", "/dev/snd/controlC0", "/dev/snd/pcmC0D0c", "/dev/snd/pcmC0D0p"], "physid": "4"}, {"claimed": True, "class": "multimedia", "description": "imxaudiomicfil", "id": "sound:1", "logicalname": ["card1", "/dev/snd/controlC1", "/dev/snd/pcmC1D0c"], "physid": "5"}, {"claimed": True, "class": "multimedia", "description": "wm8524audio", "id": "sound:2", "logicalname": ["card2", "/dev/snd/controlC2", "/dev/snd/pcmC2D0p"], "physid": "6"}, {"capabilities": {"platform": True}, "claimed": True, "class": "input", "id": "input:0", "logicalname": ["input0", "/dev/input/event0"], "physid": "7", "product": "30370000.snvs:snvs-powerkey"}, {"capabilities": {"platform": True}, "claimed": True, "class": "input", "id": "input:1", "logicalname": ["input1", "/dev/input/event1"], "physid": "8", "product": "bd718xx-pwrkey"}, {"capabilities": {"1000bt-fd": "1Gbit/s (full duplex)", "100bt": "100Mbit/s", "100bt-fd": "100Mbit/s (full duplex)", "10bt": "10Mbit/s", "10bt-fd": "10Mbit/s (full duplex)", "autonegotiation": "Auto-negotiation", "ethernet": True, "mii": "Media Independant Interface", "physical": "Physical interface", "tp": "twisted pair"}, "capacity": 1000000000, "claimed": True, "class": "network", "configuration": {"autonegotiation": "on", "broadcast": "yes", "driver": "fec", "driverversion": "Revision: 1.0", "duplex": "full", "ip": "192.168.0.40", "link": "yes", "multicast": "yes", "port": "MII", "speed": "1Gbit/s"}, "description": "Ethernet interface", "id": "network", "logicalname": "eth0", "physid": "9", "serial": "00:04:9f:06:e9:1f", "size": 1000000000, "units": "bit/s"}], "claimed": True, "class": "system", "description": "Computer", "id": "imx8mmevk", "product": "FSL i.MX8MM EVK board", "width": 64}, "updates": [{"correlation-id": "17-ed4c4efa-1f03-4a83-9bda-0c51e5b78238", "target": "imx8mmevk-lmp-17", "version": "17", "time": "2021-01-29T15:15:35Z"}, {"correlation-id": "14-07511851-67a1-4b0e-9165-1411713f6532", "target": "imx8mmevk-lmp-14", "version": "14", "time": "2021-01-29T12:44:59Z"}], "active-config": {"created-at": "2021-01-29T12:44:54", "applied-at": "2021-01-29T12:44:55", "reason": "Set Wireguard pubkey from fioconfig", "files": [{"name": "wireguard-client", "value": "enabled=0\n\npubkey=bERQE8Eq9vvlhIhq8atxsLt+qrZU9YYqnMYBOk8Nkx0=", "unencrypted": True}]}, "uuid": "2afef1d6-11a1-4d04-84c2-6d273789dccf", "owner": "600e91e5a6034fee7f021221", "factory": "milosz-rpi3", "name": "imx8mm-01", "created-at": "2021-01-29T12:44:54+00:00", "last-seen": "2021-02-01T09:50:02+00:00", "ostree-hash": "90b8cb57dd02c331b8450c846d1f3411458800eb02978b4d9a70132e63dc2f63", "target-name": "imx8mmevk-lmp-17", "current-update": "", "device-tags": ["master"], "tag": "master", "docker-apps": ["fiotest", "shellhttpd"], "network-info": {"hostname": "imx8mmevk", "local_ipv4": "192.168.0.40", "mac": "00:04:9f:06:e9:1f"}, "up-to-date": False, "public-key": "-----BEGIN PUBLIC KEY-----\nMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEoHMYa/0a8k+s0hwSkTI1wenGz1/E\nknpdM+dcpoR/0qmU8reKGsB+hD/lcb+H9r40gz1tFQREoF23tNK1Im6XIw==\n-----END PUBLIC KEY-----\n", "is-wave": False}

RUNDEF_JSON = {
  "project": "milosz-rpi3/lmp",
  "timeout": 540,
  "run_url": "https://api.foundries.io/projects/milosz-rpi3/lmp/builds/151/runs/raspberrypi3-64/",
  "frontend_url": "https://ci.foundries.io/projects/milosz-rpi3/lmp/builds/151/raspberrypi3-64/",
  "runner_url": "https://api.foundries.io/runner",
  "trigger_type": "git_poller",
  "container": "hub.foundries.io/lmp-sdk",
  "env": {
    "archive": "/archive",
    "FACTORY": "milosz-rpi3",
    "DISTRO": "lmp",
    "SOTA_PACKED_CREDENTIALS": "/var/cache/bitbake/credentials.zip",
    "SOTA_CLIENT": "aktualizr-lite",
    "IMAGE": "lmp-factory-image",
    "OSTREE_BRANCHNAME": "lmp",
    "REPO_INIT_OVERRIDES": "-b firmware -m milosz-rpi3.xml",
    "DOCKER_COMPOSE_APP_PRELOAD": "1",
    "DOCKER_COMPOSE_APP": "1",
    "OTA_LITE_TAG": "firmware:master",
    "MACHINE": "raspberrypi3-64",
    "GIT_URL": "https://source.foundries.io/factories/milosz-rpi3/lmp-manifest.git",
    "GIT_REF": "refs/heads/firmware",
    "GIT_OLD_SHA": "0000000000000000000000000000000000000000",
    "GIT_SHA": "8d52c43b2ee7f15ba6300db4e37f31db80e9cc06",
    "H_PROJECT": "milosz-rpi3/lmp",
    "H_BUILD": "151",
    "H_RUN": "raspberrypi3-64"
  },
  "persistent-volumes": {
    "bitbake": "/var/cache/bitbake"
  },
  "shared-volumes": {
    "lmp-sstate-cache": "/sstate-cache-mirror"
  },
  "host-tag": "amd64-partner",
  "console-progress": {
    "progress-pattern": "\\) INFO: Running (?:noexec )?task (?P<current>\\d+) of (?P<total>\\d+)"
  },
  "script-repo": {
    "clone-url": "https://github.com/foundriesio/ci-scripts",
    "path": "lmp/build.sh"
  }
} 

PEM_PRIV_KEY = """-----BEGIN RSA PRIVATE KEY-----
MIIG4gIBAAKCAYEAoSOe2X4wqtVSALMJa8TGf+gsZxZ1gqsrgvHpuVKElK0Kz/p8
HD3q772tgVj8SPsPuxV+IBZm99yxk7diAlHWbolqv15Ud/7yIBGBM3hvNUrT13zk
EAQAvh8DHYdgw0hfmFet8tpeJqLSPtmyt4FUNBLqs9t77uLDrGOBW/tpBNBQPUMO
TYd1/8QZWfwnkMI0cSQU9Z8qq5VDexGQq0ORzAPTTOgOTDeORdZ4rlRBmHop4QP9
ClmYuht1UDq6btc+eAHUaTVNHbu6hwUAMxVZvor4LPFULDH1I/IfGYR7OlinxKU/
JxMK2s2IkVDBTgexNmTqY1+Ar39M739qdOcnORtVCu9VZWa91Y48CVOYyg+RwM58
fkoTkgkKAxcNOKDNMLJ3QlLzdtXFQccMLCNLw8rQ1PzR3Lrgv+mOM2YXbY091vp3
G4vvfuVuK9K882PVV+KS5qkxFl7lQMKUJbkL5rmcLwMxYeiW3y+7Zf296s/2K8eY
BDO7w8DihpPfNstNAgMBAAECggGAUYl+tbse0TLEHcp6d+fIMay/2yIIMCiBCe9z
Pu08XSb6k6bB6mCCYvFtvEfU0PEJUrdbbM0pKT6pNH/Uviu+/4vVUiRfRaDhz8xL
vkmwrBzC+QUfOeNspMd4ghagpfAXPzUOthY9EfvNuzPZNPXiL79qt7vWCFkCflaT
fIHI8ECgeX9W23AyC0ulMF1hf+RlOOLzIB58LvqGfN20gJTeT4eYAhBiO7rY6QnP
YxcLYiZezpeAER6pI3MFd6Vf9PpAuhW3DQRQh+6sdz6a7sTBA8aF1uUhs1/YLFTt
UIuPPT+Ywgifl4WGxZk3OknSVnHIGKANN4cLNluAFXmloZZljgu3ic9H5Cf7/avE
TVkW95XlUb5tkfqHWC4E9sCFfsxqB3X9QGnETKGwn/fZ2Od3+NqUbLOQP4ai2rMt
LzQQlg/4nAkSQqgBaGfIwNllfoF58D0xbh6iAJE4jBS0oeNe+Gyiym33NFA1/a88
/GzzfspLVgznvXKrGrrQ2CQ96NHBAoHBANWgQTz99oZys/GYCht9Z6RMM8SPO6bs
Uicm19nxceTBJlFJWhhveMIoUOTFgB6XQG8h6K7ykW9/ncUguQhSftpgMA4+uALm
Oa8UQ2F0eXyGLsSO76jG362UNGTByck+T6GHwMFz9l9W7rZvnZpAyb2Am689YhlK
5LNdEYWYFZgjApEb8VSti0LfflSKv1rjB9lmZgUtENbALbrdN75tTeeP/8ayO2lQ
buvW+TPsrjX7/EfjRultp8qHBQcvvj1nOQKBwQDBGiDSvAsDbbzIwNOXDECHxos9
hBqltq/oqwc5s14+nJHZnl00hLxsHFNkN8jdRSED99ldcCvOyrlNN/ZttSIfFIaw
5ErpfUHjIcBDOiKGRQeWTdounL6gANB0roBBh9ECi4cSEgKdscc7KUj8EQkOAVrX
KVvSo2zyXQb/SLSS+aCKJQA+ccpkvjZNIPEbJLwA5IBpvJmL2Z/3zEBEtjCevy2X
StmDoVsGV9O4yn0YoTHypmgXT+qV0/vzu9bjULUCgcBPxdU2ynt5v3GUwTrdAxpl
zxLxzq7u6YbQGgA24aOvUbVWW3bqcw38KwPyOhJa2g50sYvrcKeApH4s88hE5FF8
iLjJSQB8DK7zwzRaOx12s8DZI6s5MnKqphJeocMRhFRGNKR1WTFibtsbg1iuFo1/
V3xLlzd/zGjU1edKJP3DXyeBOpcHEPtVEJJjTaChdvAibcuhGTAVkZRCGIPNd5HE
7BAOidYHwMJ7DT7n9fUkMaIG0kdTueATkBH/mgOHeHkCgcAD+wzoKzYy6OU2Yjs6
ZudBpUcjioCeH+j6a+QnPVpZAhNDoC8dsQrNU7woWboLTayDj21srq5IggdV3yx2
UICWkW7BYMNmks1z6DM1b5JcoDmq0IoJ4fNQCxRBA4PjVfBqFARBzBs/svV/c7ds
ctFz93Uu8ExTSEkrqd1GD/KhAQJdNqwNnXzlnMIzztUJkTVK82ruQxQLPP4+Nniw
sezIqPpAnytiukXNGKxlp87yXghQjzugF2anlgogmSOx5e0CgcAwNUCcw3RFxFyn
sxt/1aF1HiobysjjcmoZZPvKjW74jeTKyVyg4QWgPrkTuEUhS5bYklHq/7zcRdIT
eeRvRCCSW+jtmYryvSEwPcg2bX+CEhEzrJRxkp2J3wPXxqvh3ybMQT4a1712sDP2
IBi3HwqE6jVxnl9mOZPi+dnUmiOrRGrSfx7Jrt5lZL27ltt7M8C90o5anqWyqwFW
VK3ZSSn5+31zjyuZ4+oQpTFWn6g+7IlVQHl56/BoBate4OfxAKs=
-----END RSA PRIVATE KEY-----"""

PEM_PRIV_KEY_ED25519 = """-----BEGIN PRIVATE KEY-----
MC4CAQAwBQYDK2VwBCIEIPw4JlEEdsmBRN0dKwJpXQgTwdnddxWSYqBvGwvkZcfl
-----END PRIVATE KEY-----"""


LMP_API_BUILDS = {'limit': 25,
                  'page': 0,
                  'pages': 14,
                  'total': 333,
                  'next': 'http://example.com/?page=1',
                  'builds': [
                      {'build_id': 2564,
                       'url': 'https://api.foundries.io/projects/lmp/builds/2564/',
                       'status': 'PASSED',
                       'web_url': 'https://ci.foundries.io/projects/lmp/builds/2564',
                       'trigger_name': 'Code Review',
                       'created': '2024-03-28T11:29:15+00:00',
                       'runs': []}
                      ]
                  }

LMP_CI_BUILD_DETAILS = {'build_id': 2564, 'url': 'https://api.foundries.io/projects/lmp/builds/2564/', 'status': 'PASSED', 'runs': [{'name': 'lmp-sdk', 'run_url': 'https://api.foundries.io/projects/lmp/builds/2564/runs/lmp-sdk/', 'status': 'PASSED'}], 'web_url': 'https://ci.foundries.io/projects/lmp/builds/2564', 'runs_url': 'https://api.foundries.io/projects/lmp/builds/2557/runs/', 'reason': 'GitHub PR(427): pull_request, https://github.com/foundriesio/lmp-manifest/pull/427', 'annotation': None}


class ProjectTest(TestCase):
    def setUp(self):
        self.lavabackend1 = LAVABackend.objects.create(
            name="testLavaBackend1",
            lava_url="http://lava.example.com/api/v0.2/",
            lava_api_token="lavatoken",
        )
        self.squadbackend1 = SQUADBackend.objects.create(
            name="testSquadBackend1",
            squad_url="https://squad.example.com/",
            squad_token="squadtoken"
        )
        self.project = Project.objects.create(
            name="testProject1",
            secret="webhooksecret",
            lava_backend=self.lavabackend1,
            squad_backend=self.squadbackend1,
            squad_group="squadgroup",
            fio_api_token="fio_api_token1"
        )
        self.build = Build.objects.create(
            url="https://example.com/build/1/",
            project=self.project,
            build_id="1"
        )

    @patch('requests.post')
    def test_submit_lava_job(self, post_mock):
        definition = """
        device_type: foo
        job_name: lava test definition
        """
        response_mock = MagicMock()
        response_mock.status_code = 201
        response_mock.json.return_value = {'job_ids': ['123']}
        post_mock.return_value = response_mock

        ret_list = self.project.submit_lava_job(definition)
        if not settings.DEBUG_LAVA_SUBMIT:
            post_mock.assert_called()
            self.assertEqual(ret_list, ['123'])

    @patch('requests.post')
    def test_squad_watch_job(self, post_mock):
        test_job_id = "123"
        environment = "environment"
        response_mock = MagicMock()
        response_mock.status_code = 201
        response_mock.text = "321"
        post_mock.return_value = response_mock

        squad_watch_job_response = self.project.watch_qa_reports_job(self.build, environment, test_job_id)
        if not settings.DEBUG_SQUAD_SUBMIT:
            self.assertEqual(squad_watch_job_response.text, "321")
            post_mock.assert_called_with(
                f"{self.squadbackend1.squad_url}api/watchjob/{self.project.squad_group}/{self.project.name}/{self.build.build_id}/{environment}",
                headers={'Auth-Token': self.squadbackend1.squad_token},
                data={'testjob_id': test_job_id, 'backend': self.squadbackend1.name},
                timeout=DEFAULT_TIMEOUT
            )
        else:
            self.assertEqual(squad_watch_job_response.text, test_job_id)
        self.assertEqual(squad_watch_job_response.status_code, 201)

    @patch('requests.post')
    def test_squad_watch_job_different_name(self, post_mock):
        self.project.qa_reports_project_name = "project_qa_reports"
        self.project.save()
        test_job_id = "123"
        environment = "environment"
        response_mock = MagicMock()
        response_mock.status_code = 201
        response_mock.text = "321"
        post_mock.return_value = response_mock

        squad_watch_job_response = self.project.watch_qa_reports_job(self.build, environment, test_job_id)
        if not settings.DEBUG_SQUAD_SUBMIT:
            self.assertEqual(squad_watch_job_response.text, "321")
            post_mock.assert_called_with(
                f"{self.squadbackend1.squad_url}api/watchjob/{self.project.squad_group}/{self.project.qa_reports_project_name}/{self.build.build_id}/{environment}",
                headers={'Auth-Token': self.squadbackend1.squad_token},
                data={'testjob_id': test_job_id, 'backend': self.squadbackend1.name},
                timeout=DEFAULT_TIMEOUT
            )
        else:
            self.assertEqual(squad_watch_job_response.text, test_job_id)
        self.assertEqual(squad_watch_job_response.status_code, 201)

    @patch('requests.put')
    @patch('requests.get')
    def test_squad_update_job(self, get_mock, put_mock):
        squad_job_id = "123"
        squad_job_name = "foobar"
        squad_job_definition = "definition"
        get_response_mock = MagicMock()
        get_response_mock.status_code = 200
        get_response_mock.json = MagicMock(return_value={})
        get_mock.return_value = get_response_mock
        response_mock = MagicMock()
        response_mock.status_code = 200
        response_mock.text = "321"
        put_mock.return_value = response_mock

        squad_watch_job_response = self.project.squad_backend.update_testjob(squad_job_id, squad_job_name, squad_job_definition)
        if not settings.DEBUG_SQUAD_SUBMIT:
            get_mock.assert_called_with(
                f"{self.squadbackend1.squad_url}api/testjobs/{squad_job_id}",
                headers={'Authorization': f"Token {self.squadbackend1.squad_token}"}
            )
            self.assertEqual(squad_watch_job_response.text, "321")
            self.assertEqual(squad_watch_job_response.status_code, 200)
            put_mock.assert_called_with(
                f"{self.squadbackend1.squad_url}api/testjobs/{squad_job_id}",
                headers={'Authorization': f"Token {self.squadbackend1.squad_token}"},
                data={'definition': squad_job_definition, 'name': squad_job_name}
            )

class LAVADeviceTest(TestCase):
    def setUp(self):
        self.lavabackend1 = LAVABackend.objects.create(
            name="testLavaBackend1",
            lava_url="http://lava.example.com/api/v0.2/",
            lava_api_token="lavatoken",
        )
        self.project = Project.objects.create(
            name="testProject1",
            secret="webhooksecret",
            lava_backend=self.lavabackend1,
            fio_api_token="fio_api_token1"
        )
        self.device_type1 = LAVADeviceType.objects.create(
            name="device-type-1",
            net_interface="eth0",
            project=self.project,
        )
        self.lava_device1 = LAVADevice.objects.create(
            device_type = self.device_type1,
            name = "device-type-1-1",
            auto_register_name = "ota_device_1",
            project = self.project,
        )

    @patch("requests.get")
    def test_get_current_target(self, get_mock):
        response_mock = MagicMock()
        response_mock.status_code = 200
        response_mock.json.return_value = TARGET_DICT
        get_mock.return_value = response_mock
        target = self.lava_device1.get_current_target()
        get_mock.assert_called_with(
            f'https://api.foundries.io/ota/devices/{self.lava_device1.auto_register_name}/',
            headers={'OSF-TOKEN': self.project.fio_api_token},
            params={"factory": self.project.name})
        self.assertEqual(target, TARGET_DICT)

    @patch("requests.delete")
    def test_remove_from_factory(self, delete_mock):
        response_mock = MagicMock()
        response_mock.status_code = 200
        delete_mock.return_value = response_mock
        self.lava_device1.remove_from_factory(self.project.name)
        delete_mock.assert_called_with(
            f'https://api.foundries.io/ota/devices/{self.lava_device1.auto_register_name}/',
            headers={'OSF-TOKEN': self.project.fio_api_token},
            params={"factory": self.project.name})

    @patch("requests.delete")
    def test_remove_from_factory_fail(self, delete_mock):
        response_mock = MagicMock()
        response_mock.status_code = 400
        delete_mock.return_value = response_mock
        response = self.lava_device1.remove_from_factory(self.project.name)
        delete_mock.assert_called_with(
            f'https://api.foundries.io/ota/devices/{self.lava_device1.auto_register_name}/',
            headers={'OSF-TOKEN': self.project.fio_api_token},
            params={"factory": self.project.name})
        self.assertEqual({}, response)

class TaskTest(TestCase):
    def setUp(self):
        self.lavabackend1 = LAVABackend.objects.create(
            name="testLavaBackend1",
            lava_url="http://lava.example.com/api/v0.2/",
            lava_api_token="lavatoken",
        )
        self.squadbackend1 = SQUADBackend.objects.create(
            name="testSquadBackend1",
            squad_url="https://squad.example.com/",
            squad_token="squadtoken"
        )
        self.project = Project.objects.create(
            name="testProject1",
            secret="webhooksecret",
            lava_backend=self.lavabackend1,
            squad_backend=self.squadbackend1,
            squad_group="squadgroup",
            fio_api_token="fio_api_token1",
            fio_repository_token="fio_repository_token1",
            create_ota_commit=True
        )
        self.project_meds = Project.objects.create(
            name="testProjectMeds1",
            secret="webhooksecret",
            lava_backend=self.lavabackend1,
            squad_backend=self.squadbackend1,
            squad_group="squadgroup",
            fio_api_token="fio_api_token_meds1",
            fio_repository_token="fio_repository_token_meds1",
            create_ota_commit=True,
            fio_meds_domain="meds.com"
        )
        self.project_partner = Project.objects.create(
            name="testProjectPartner1",
            secret="webhooksecret",
            lava_backend=self.lavabackend1,
            squad_backend=self.squadbackend1,
            squad_group="squadgroup",
            fio_api_token="fio_api_token_partner1",
            fio_repository_token="fio_repository_token_partner1",
            create_ota_commit=True,
            fio_lmp_manifest_url="https://github.com/example/repository"
        )
        self.project_rolling = Project.objects.create(
            name="testProject2",
            secret="webhooksecret",
            lava_backend=self.lavabackend1,
            squad_backend=self.squadbackend1,
            squad_group="squadgroup",
            fio_api_token="fio_api_token2",
            fio_repository_token="fio_repository_token2"
        )
        self.project_testplan = Project.objects.create(
            name="testProjectTestplan1",
            secret="webhooksecret",
            lava_backend=self.lavabackend1,
            squad_backend=self.squadbackend1,
            squad_group="squadgroup",
            fio_api_token="fio_api_token3",
            fio_repository_token="fio_repository_token3"
        )
        self.project_lmp = Project.objects.create(
            name="lmp",
            secret="webhooksecret",
            lava_backend=self.lavabackend1,
            squad_backend=self.squadbackend1,
            squad_group="squadgroup",
            fio_api_token="fio_api_token3",
            fio_repository_token="fio_repository_token3"
        )
        self.old_previous_build = Build.objects.create(
            url="https://example.com/build/1/",
            project=self.project,
            build_id="1"
        )
        self.previous_build = Build.objects.create(
            url="https://example.com/build/1/",
            project=self.project,
            build_id="2"
        )
        self.old_previous_build_run_1 = Run.objects.create(
            build=self.old_previous_build,
            device_type="imx8mmevk",
            ostree_hash="previousHash",
            run_name="imx8mmevk"
        )
        self.old_previous_build_run_2 = Run.objects.create(
            build=self.old_previous_build,
            device_type="raspberrypi4-64",
            ostree_hash="previousHash",
            run_name="raspberrypi4-64"
        )
        self.previous_build_run_1 = Run.objects.create(
            build=self.previous_build,
            device_type="imx8mmevk",
            ostree_hash="previousHash",
            run_name="imx8mmevk"
        )
        self.previous_build_run_2 = Run.objects.create(
            build=self.previous_build,
            device_type="raspberrypi4-64",
            ostree_hash="previousHash",
            run_name="raspberrypi4-64"
        )

        self.build = Build.objects.create(
            url="https://example.com/build/2/",
            project=self.project,
            build_id="4"
        )
        self.build_run = Run.objects.create(
            build=self.build,
            device_type="imx8mmevk",
            ostree_hash="currentHash",
            run_name="imx8mmevk"
        )
        self.build_run_2 = Run.objects.create(
            build=self.build,
            device_type="raspberrypi4-64",
            ostree_hash="currentHash",
            run_name="raspberrypi4-64"
        )
        self.build_rolling = Build.objects.create(
            url="https://example.com/build/2/",
            project=self.project_rolling,
            build_id="2"
        )
        self.build_run_rolling = Run.objects.create(
            build=self.build_rolling,
            device_type="imx8mmevk",
            ostree_hash="currentHash",
            run_name="imx8mmevk"
        )
        self.build_testplan = Build.objects.create(
            url="https://example.com/build/3/",
            project=self.project_testplan,
            build_id="3"
        )
        self.build_testplan_ota = Build.objects.create(
            url="https://example.com/build/4/",
            project=self.project_testplan,
            build_id="4"
        )
        self.build_testplan_static = Build.objects.create(
            url="https://example.com/build/5/",
            project=self.project_testplan,
            static_from=self.build_testplan,
            static_to=self.build_testplan_ota,
            build_id="5"
        )
        self.build_testplan_containers = Build.objects.create(
            url="https://example.com/build/5/",
            project=self.project_testplan,
            build_type=Build.BUILD_TYPE_CONTAINERS,
            build_id="6"
        )

        self.build_run_testplan1 = Run.objects.create(
            build=self.build_testplan,
            device_type="imx8mmevk",
            ostree_hash="currentHash",
            run_name="imx8mmevk"
        )

        self.device_type1 = LAVADeviceType.objects.create(
            name="imx8mmevk",
            net_interface="eth0",
            project=self.project,
        )
        self.device_type2 = LAVADeviceType.objects.create(
            name="raspberrypi4-64",
            net_interface="eth0",
            project=self.project,
        )
        self.device_type3 = LAVADeviceType.objects.create(
            name="imx8mp-lpddr4-evk",
            net_interface="eth0",
            project=self.project,
        )
        self.device_type4 = LAVADeviceType.objects.create(
            name="imx8mmevk-sec",
            net_interface="eth0",
            project=self.project,
        )
        self.device_type5 = LAVADeviceType.objects.create(
            name="imx6ullevk",
            net_interface="eth0",
            project=self.project,
        )
        self.device_type6 = LAVADeviceType.objects.create(
            name="imx8mq-evk",
            net_interface="eth0",
            project=self.project,
        )
        self.device_type7 = LAVADeviceType.objects.create(
            name="intel-corei7-64",
            net_interface="eth0",
            project=self.project,
        )
        self.device_type_testplan1 = LAVADeviceType.objects.create(
            name="imx8mmevk",
            net_interface="eth0",
            project=self.project_testplan,
        )
        self.device_type_testplan2 = LAVADeviceType.objects.create(
            name="imx8mmevk-sec",
            net_interface="eth0",
            project=self.project_testplan,
        )
        self.device_type_testplan3 = LAVADeviceType.objects.create(
            name="imx93evk",
            net_interface="eth0",
            project=self.project_testplan,
        )

        self.device_type_lmp1 = LAVADeviceType.objects.create(
            name="imx8mmevk",
            net_interface="eth0",
            project=self.project_lmp,
        )

        self.lava_device1 = LAVADevice.objects.create(
            device_type = self.device_type1,
            name = "imx8mmevk-1",
            auto_register_name = "ota_device_1",
            project = self.project,
        )
        self.lava_device2 = LAVADevice.objects.create(
            device_type = self.device_type2,
            name = "raspberrypi4-64-1",
            auto_register_name = "ota_device_2",
            project = self.project,
        )
        self.lava_device3 = LAVADevice.objects.create(
            device_type = self.device_type3,
            name = "imx8mp-lpddr4-evk-01",
            auto_register_name = "ota_device_3",
            project = self.project,
        )
        self.lava_device4 = LAVADevice.objects.create(
            device_type = self.device_type4,
            name = "imx8mmevk-sec-01",
            auto_register_name = "ota_device_4",
            project = self.project,
        )
        self.lava_device5 = LAVADevice.objects.create(
            device_type = self.device_type5,
            name = "imx6ullevk-01",
            auto_register_name = "ota_device_5",
            project = self.project,
        )
        self.lava_device6 = LAVADevice.objects.create(
            device_type = self.device_type6,
            name = "imx8mq-evk-01",
            auto_register_name = "ota_device_6",
            project = self.project,
        )
        self.lava_device7 = LAVADevice.objects.create(
            device_type = self.device_type7,
            name = "qemu-01",
            auto_register_name = "ota_device_7",
            project = self.project,
        )
        # testplan
        self.lava_device_testplan1 = LAVADevice.objects.create(
            device_type = self.device_type_testplan1,
            name = "imx8mmevk-1",
            auto_register_name = "ota_device_1",
            project = self.project_testplan,
        )
        self.lava_device_testplan2 = LAVADevice.objects.create(
            device_type = self.device_type_testplan2,
            name = "imx8mmevk-sec-1",
            auto_register_name = "ota_device_2",
            project = self.project_testplan,
        )
        self.lava_device_testplan3 = LAVADevice.objects.create(
            device_type = self.device_type_testplan3,
            name = "imx93evk-1",
            auto_register_name = "ota_device_3",
            project = self.project_testplan,
        )
        self.testplan1 = TestPlan.objects.create(
            name = "testplan_imx8mm",
            lava_device_type = "imx8mmevk"
        )
        self.testplan1.save()
        self.testjob_imx8mm1 = TestJob.objects.create(
            priority=50
        )
        self.testjob_imx8mm1.save()
        self.testplan1.testjobs.add(self.testjob_imx8mm1)
        self.testjob_imx8mm3 = TestJob.objects.create(
            priority=50,
            is_static_delta_job=True
        )
        self.testjob_imx8mm3.save()
        self.testplan1.testjobs.add(self.testjob_imx8mm3)
        self.testplan1.save()

        self.testplan1.save()
        self.project_testplan.testplans.add(self.testplan1)

        self.testplan2 = TestPlan.objects.create(
            name = "testplan_el2go",
            lava_device_type = "imx8mmevk-sec"
        )
        self.testplan2.save()
        self.testjob_imx8mm2 = TestJob.objects.create(
            priority=50,
            is_el2go_job=True
        )
        self.testjob_imx8mm2.save()
        self.testplan2.testjobs.add(self.testjob_imx8mm2)
        self.testplan2.save()
        self.project_testplan.testplans.add(self.testplan2)
        self.project_lmp.testplans.add(self.testplan1)

        self.testplan3 = TestPlan.objects.create(
            name = "testplan_ota",
            lava_device_type = "imx93evk"
        )
        self.testplan3.save()
        self.testjob_imx8mm3_1 = TestJob.objects.create(
            name="job1",
            priority=50,
            is_ota_job=True,
            is_downgrade_job=False,
        )
        self.testjob_imx8mm3_2 = TestJob.objects.create(
            name="job2",
            priority=50,
            is_ota_job=True,
            is_downgrade_job=True,
        )
        self.testjob_imx8mm3_3 = TestJob.objects.create(
            name="job3",
            priority=50,
            is_ota_job=False,
            is_downgrade_job=False,
            is_assemble_image_job=True,
        )

        self.testjob_imx8mm3_1.save()
        self.testjob_imx8mm3_2.save()
        self.testjob_imx8mm3_3.save()
        self.testplan3.testjobs.add(self.testjob_imx8mm3_1)
        self.testplan3.testjobs.add(self.testjob_imx8mm3_2)
        self.testplan3.testjobs.add(self.testjob_imx8mm3_3)
        self.testplan3.save()
        self.project_testplan.testplans.add(self.testplan3)


        # notifications
        definition_lavajob1 = yaml.dump({"actions": [{"boot": {"prompts": ["root@ota_device_1"]}}]})
        self.lavajob1 = LAVAJob.objects.create(
            job_id=1,
            device=self.lava_device_testplan1,
            requested_device_type=self.device_type_testplan1,
            project=self.project_testplan,
            job_type=LAVAJob.JOB_LAVA,
            definition=definition_lavajob1
        )
        definition_lavajob2 = yaml.dump({"actions": [{"boot": {"prompts": ["root@ota_device_2"]}}]})
        self.lavajob2 = LAVAJob.objects.create(
            job_id=2,
            device=self.lava_device_testplan2,
            requested_device_type=self.device_type_testplan2,
            project=self.project_testplan,
            job_type=LAVAJob.JOB_EL2GO,
            definition=definition_lavajob2
        )

    @patch('requests.get')
    @patch('conductor.core.models.SQUADBackend.create_build')
    @patch('conductor.core.models.SQUADBackend.submit_lava_job')
    def test_lmp_pr_boot_test(self, squad_submit_job_mock, squad_create_build_mock, get_mock):
        get_response_dict = {
            "head": {"sha": "deadbeef"},
            "labels": [
            ]
        }
        get_response = MagicMock()
        type(get_response).status_code = PropertyMock(return_value=200)
        get_response.json = MagicMock(return_value=get_response_dict)
        get_mock.return_value = get_response

        build_desc = json.loads(LMP_BUILD_JSON)
        schedule_lmp_pr_tests(build_desc)
        get_mock.assert_called()
        squad_create_build_mock.assert_called()
        squad_submit_job_mock.assert_called()
    @patch('requests.get')

    @patch('conductor.core.models.SQUADBackend.create_build')
    @patch('conductor.core.models.SQUADBackend.submit_lava_job')
    def test_lmp_pr_boot_test_labels(self, squad_submit_job_mock, squad_create_build_mock, get_mock):
        get_response_dict = {
            "head": {"sha": "deadbeef"},
            "labels": [
                {"name": "foobar"}
            ]
        }
        get_response = MagicMock()
        type(get_response).status_code = PropertyMock(return_value=200)
        get_response.json = MagicMock(return_value=get_response_dict)
        get_mock.return_value = get_response

        build_desc = json.loads(LMP_BUILD_JSON)
        schedule_lmp_pr_tests(build_desc)
        get_mock.assert_called()
        squad_create_build_mock.assert_called()
        squad_submit_job_mock.assert_called()

    @patch('requests.get')
    @patch('conductor.core.models.SQUADBackend.create_build')
    @patch('conductor.core.models.SQUADBackend.submit_lava_job')
    def test_lmp_pr_boot_test_skip_qa(self, squad_submit_job_mock, squad_create_build_mock, get_mock):
        get_response_dict = {
            "head": {"sha": "deadbeef"},
            "labels": [
                {"name": "skip-qa"}
            ]
        }
        get_response = MagicMock()
        type(get_response).status_code = PropertyMock(return_value=200)
        get_response.json = MagicMock(return_value=get_response_dict)
        get_mock.return_value = get_response
        build_desc = json.loads(LMP_BUILD_JSON)
        schedule_lmp_pr_tests(build_desc)
        get_mock.assert_called()
        squad_create_build_mock.assert_not_called()
        squad_submit_job_mock.assert_not_called()

    @patch('conductor.core.tasks.schedule_lmp_pr_tests.delay')
    @patch('conductor.core.tasks.update_build_commit_id.delay')
    @patch('conductor.core.models.Project.get_api_builds', return_value=LMP_API_BUILDS)
    @patch('conductor.core.models.Project.ci_build_details', return_value=LMP_CI_BUILD_DETAILS)
    def test_fetch_lmp_code_review(self, mock_build_details, mock_api_builds, mock_update, mock_schedule):
        fetch_lmp_code_review()
        mock_build_details.assert_called_with(LMP_API_BUILDS["builds"][0]["build_id"])
        mock_api_builds.assert_called()
        mock_schedule.assert_called_with(LMP_CI_BUILD_DETAILS)
        s_build_id = Build.objects.last().id
        mock_update.assert_called_with(s_build_id, 'https://api.foundries.io/projects/lmp/builds/2564/runs/lmp-sdk/')

    @patch('conductor.core.tasks.schedule_lmp_pr_tests.delay')
    @patch('conductor.core.models.Project.get_api_builds')
    @patch('conductor.core.models.Project.ci_build_details', return_value=LMP_CI_BUILD_DETAILS)
    def test_fetch_lmp_code_review_running(self, mock_build_details, mock_api_builds, mock_schedule):
        api_builds_running = LMP_API_BUILDS
        api_builds_running["builds"][0]["status"] = "RUNNING"
        mock_api_builds.return_value = api_builds_running
        fetch_lmp_code_review()
        mock_api_builds.assert_called()
        mock_build_details.assert_not_called()
        mock_schedule.assert_not_called()

    @patch('conductor.core.tasks.schedule_lmp_pr_tests.delay')
    @patch('conductor.core.models.Project.get_api_builds')
    @patch('conductor.core.models.Project.ci_build_details', return_value=LMP_CI_BUILD_DETAILS)
    def test_fetch_lmp_code_review_wrong_trigger(self, mock_build_details, mock_api_builds, mock_schedule):
        api_builds_running = LMP_API_BUILDS
        api_builds_running["builds"][0]["trigger_name"] = "Foo"
        mock_api_builds.return_value = api_builds_running
        fetch_lmp_code_review()
        mock_api_builds.assert_called()
        mock_build_details.assert_not_called()
        mock_schedule.assert_not_called()

    @patch('conductor.core.models.LAVADevice.add_to_el2go')
    @patch('conductor.core.models.LAVADevice.remove_from_el2go')
    @patch('conductor.core.models.LAVADevice.remove_from_factory')
    def test_process_testjob_notification_lava_missing_job_id(
            self,
            remove_factory_mock,
            remove_el2go_mock,
            add_el2go_mock):
        event_data = {
            "job": 3,
            "device": self.lava_device_testplan1.name,
            "state": "Running",
        }
        process_testjob_notification(event_data)
        add_el2go_mock.assert_not_called()
        remove_el2go_mock.assert_not_called()
        remove_factory_mock.assert_not_called()

    @patch('conductor.core.models.LAVADevice.add_to_el2go')
    @patch('conductor.core.models.LAVADevice.remove_from_el2go')
    @patch('conductor.core.models.LAVADevice.remove_from_factory')
    def test_process_testjob_notification_lava_running(
            self,
            remove_factory_mock,
            remove_el2go_mock,
            add_el2go_mock):
        event_data = {
            "job": self.lavajob1.job_id,
            "device": self.lava_device_testplan1.name,
            "state": "Running",
        }
        process_testjob_notification(event_data)
        add_el2go_mock.assert_not_called()
        remove_el2go_mock.assert_not_called()
        remove_factory_mock.assert_called()

    @patch('conductor.core.models.LAVADevice.add_to_el2go')
    @patch('conductor.core.models.LAVADevice.remove_from_el2go')
    @patch('conductor.core.models.LAVADevice.remove_from_factory')
    def test_process_testjob_notification_lava_finished_complete(
            self,
            remove_factory_mock,
            remove_el2go_mock,
            add_el2go_mock):
        event_data = {
            "job": self.lavajob1.job_id,
            "device": self.lava_device_testplan1.name,
            "state": "Finished",
            "health": "Complete"
        }
        process_testjob_notification(event_data)
        add_el2go_mock.assert_not_called()
        remove_el2go_mock.assert_not_called()
        remove_factory_mock.assert_not_called()

    @patch('conductor.core.models.LAVADevice.add_to_el2go')
    @patch('conductor.core.models.LAVADevice.remove_from_el2go')
    @patch('conductor.core.models.LAVADevice.remove_from_factory')
    def test_process_testjob_notification_lava_finished_incomplete(
            self,
            remove_factory_mock,
            remove_el2go_mock,
            add_el2go_mock):
        event_data = {
            "job": self.lavajob1.job_id,
            "device": self.lava_device_testplan1.name,
            "state": "Finished",
            "health": "Incomplete"
        }
        process_testjob_notification(event_data)
        add_el2go_mock.assert_not_called()
        remove_el2go_mock.assert_not_called()
        remove_factory_mock.assert_not_called()

    @patch('conductor.core.models.LAVADevice.add_to_el2go')
    @patch('conductor.core.models.LAVADevice.remove_from_el2go')
    @patch('conductor.core.models.LAVADevice.remove_from_factory')
    def test_process_testjob_notification_el2go_running(
            self,
            remove_factory_mock,
            remove_el2go_mock,
            add_el2go_mock):
        event_data = {
            "job": self.lavajob2.job_id,
            "device": self.lava_device_testplan2.name,
            "state": "Running"
        }
        process_testjob_notification(event_data)
        add_el2go_mock.assert_called()
        remove_el2go_mock.assert_called()
        remove_factory_mock.assert_called()

    @patch('conductor.core.models.LAVADevice.add_to_el2go')
    @patch('conductor.core.models.LAVADevice.remove_from_el2go')
    @patch('conductor.core.models.LAVADevice.remove_from_factory')
    def test_process_testjob_notification_el2go_finished(
            self,
            remove_factory_mock,
            remove_el2go_mock,
            add_el2go_mock):
        event_data = {
            "job": self.lavajob2.job_id,
            "device": self.lava_device_testplan2.name,
            "state": "Finished",
            "health": "Complete"
        }
        process_testjob_notification(event_data)
        add_el2go_mock.assert_not_called()
        remove_el2go_mock.assert_called()
        remove_factory_mock.assert_not_called()

    @patch('conductor.core.models.Build.get_lmp_commit_url', return_value="https://example.com/aabbccddeeff")
    @patch('conductor.core.tasks._get_os_tree_hash', return_value="someHash1")
    @patch('conductor.core.models.SQUADBackend.update_testjob')
    @patch('conductor.core.models.Project.watch_qa_reports_job')
    @patch('conductor.core.models.Project.submit_lava_job', return_value=[123])
    @patch('conductor.core.tasks.update_build_reason')
    def test_create_build_run_testplan(self, update_build_reason_mock, submit_lava_job_mock, watch_qa_reports_mock, update_testjob_mock, get_hash_mock, build_lmp_commit_mock):
        response_mock = MagicMock()
        response_mock.status_code = 201
        response_mock.text = "321"
        watch_qa_reports_mock.return_value = response_mock
        run_name = "imx8mmevk"
        self.build_testplan.build_reason = "Hello world"
        self.build_testplan.build_type = Build.BUILD_TYPE_REGULAR
        self.build_testplan.lmp_commit = "aabbccddeeff"
        self.build_testplan.save()
        create_build_run(self.build_testplan.id, run_name)
        update_build_reason_mock.assert_not_called()
        submit_lava_job_mock.assert_called()
        watch_qa_reports_mock.assert_called()
        update_testjob_mock.assert_called()
        assert 1 == submit_lava_job_mock.call_count
        get_hash_mock.assert_called()
        assert 1 == get_hash_mock.call_count
        build_lmp_commit_mock.assert_called()

    @patch('conductor.core.tasks._get_os_tree_hash', return_value="someHash1")
    @patch('conductor.core.models.SQUADBackend.update_testjob')
    @patch('conductor.core.models.Project.watch_qa_reports_job')
    @patch('conductor.core.models.Project.submit_lava_job', return_value=[123])
    @patch('conductor.core.tasks.update_build_reason')
    def test_create_build_run_testplan_no_merge_commit(self, update_build_reason_mock, submit_lava_job_mock, watch_qa_reports_mock, update_testjob_mock, get_hash_mock):
        response_mock = MagicMock()
        response_mock.status_code = 201
        response_mock.text = "321"
        watch_qa_reports_mock.return_value = response_mock
        run_name = "imx8mmevk"
        self.build_testplan.build_reason = "Hello world"
        self.build_testplan.build_type = Build.BUILD_TYPE_REGULAR
        self.build_testplan.is_merge_commit = False
        self.build_testplan.save()
        self.build_testplan.project.test_on_merge_only = True
        self.build_testplan.project.save()
        create_build_run(self.build_testplan.id, run_name)
        update_build_reason_mock.assert_not_called()
        submit_lava_job_mock.assert_not_called()
        watch_qa_reports_mock.assert_not_called()
        update_testjob_mock.assert_not_called()
        get_hash_mock.assert_not_called()

    @patch('conductor.core.tasks._get_os_tree_hash', return_value="someHash1")
    @patch('conductor.core.models.SQUADBackend.update_testjob')
    @patch('conductor.core.models.Project.watch_qa_reports_job')
    @patch('conductor.core.models.Project.submit_lava_job', return_value=[123])
    @patch('conductor.core.tasks.update_build_reason')
    def test_create_build_run_testplan_el2go(self, update_build_reason_mock, submit_lava_job_mock, watch_qa_reports_mock, update_testjob_mock, get_hash_mock):
        response_mock = MagicMock()
        response_mock.status_code = 201
        response_mock.text = "321"
        watch_qa_reports_mock.return_value = response_mock
        run_name = "imx8mmevk-sec"
        self.build_testplan.build_reason = "Hello world"
        self.build_testplan.build_type = Build.BUILD_TYPE_REGULAR
        self.build_testplan.save()
        create_build_run(self.build_testplan.id, run_name)
        update_build_reason_mock.assert_not_called()
        submit_lava_job_mock.assert_called()
        watch_qa_reports_mock.assert_called()
        update_testjob_mock.assert_called()
        assert 1 == submit_lava_job_mock.call_count
        get_hash_mock.assert_called()
        assert 1 == get_hash_mock.call_count

    @patch('conductor.core.tasks._get_os_tree_hash', return_value="someHash1")
    @patch('conductor.core.models.SQUADBackend.update_testjob')
    @patch('conductor.core.models.Project.watch_qa_reports_job')
    @patch('conductor.core.models.Project.submit_lava_job', return_value=[123])
    @patch('conductor.core.tasks.update_build_reason')
    def test_create_build_run_testplan_ota(self, update_build_reason_mock, submit_lava_job_mock, watch_qa_reports_mock, update_testjob_mock, get_hash_mock):
        response_mock = MagicMock()
        response_mock.status_code = 201
        response_mock.text = "321"
        watch_qa_reports_mock.return_value = response_mock
        run_name = "imx93evk"
        self.build_testplan_static.build_reason = "Hello world"
        self.build_testplan_static.build_type = Build.BUILD_TYPE_OTA
        self.build_testplan_static.save()
        create_build_run(self.build_testplan_static.id, run_name)
        update_build_reason_mock.assert_not_called()
        submit_lava_job_mock.assert_called()
        watch_qa_reports_mock.assert_called()
        update_testjob_mock.assert_called()
        assert 2 == submit_lava_job_mock.call_count
        get_hash_mock.assert_called()
        assert 2 == get_hash_mock.call_count

    @patch('conductor.core.tasks._get_os_tree_hash', return_value="someHash1")
    @patch('conductor.core.models.SQUADBackend.update_testjob')
    @patch('conductor.core.models.Project.watch_qa_reports_job')
    @patch('conductor.core.models.Project.submit_lava_job', return_value=[123])
    @patch('conductor.core.tasks.update_build_reason')
    def test_create_build_run_testplan_containers(self, update_build_reason_mock, submit_lava_job_mock, watch_qa_reports_mock, update_testjob_mock, get_hash_mock):
        response_mock = MagicMock()
        response_mock.status_code = 201
        response_mock.text = "321"
        watch_qa_reports_mock.return_value = response_mock
        run_name = "imx93evk"
        self.build_testplan_containers.build_reason = "Hello world"
        self.build_testplan_containers.save()
        create_build_run(self.build_testplan_containers.id, run_name)
        update_build_reason_mock.assert_not_called()
        submit_lava_job_mock.assert_called()
        watch_qa_reports_mock.assert_called()
        update_testjob_mock.assert_called()
        assert 3 == submit_lava_job_mock.call_count
        get_hash_mock.assert_called()
        assert 3 == get_hash_mock.call_count


    @patch('conductor.core.tasks._get_os_tree_hash', return_value="someHash1")
    @patch('conductor.core.models.SQUADBackend.watch_lava_job', return_value=None)
    @patch('conductor.core.models.Project.submit_lava_job', return_value=[123])
    @patch('conductor.core.tasks.update_build_reason')
    def test_create_build_run_no_qareports(self, update_build_reason_mock, submit_lava_job_mock, watch_lava_job_mock, get_hash_mock):
        self.project_testplan.squad_backend = None
        self.project_testplan.save()
        run_name = "imx8mmevk"
        self.build_testplan.build_reason = "Hello world"
        self.build_testplan.build_type = Build.BUILD_TYPE_REGULAR
        self.build_testplan.save()
        create_build_run(self.build_testplan.id, run_name)
        update_build_reason_mock.assert_not_called()
        submit_lava_job_mock.assert_called()
        watch_lava_job_mock.assert_not_called()
        assert 1 == submit_lava_job_mock.call_count
        get_hash_mock.assert_called()
        assert 1 == get_hash_mock.call_count

    @patch('conductor.core.tasks._get_os_tree_hash', return_value="someHash1")
    @patch('conductor.core.models.Project.watch_qa_reports_job', return_value=None)
    @patch('conductor.core.models.Project.submit_lava_job', return_value=[123])
    @patch('conductor.core.tasks.update_build_reason')
    def test_create_build_run_no_reason(self, update_build_reason_mock, submit_lava_job_mock, watch_qa_reports_mock, get_hash_mock):
        run_name = "imx8mmevk"
        with self.assertRaises(celery.exceptions.Retry) as context:
            create_build_run(self.build.id, run_name)
            update_build_reason_mock.assert_called()
            submit_lava_job_mock.assert_not_called()
            watch_qa_reports_mock.assert_not_called()

    @patch('conductor.core.tasks._get_os_tree_hash', return_value=None)
    @patch('conductor.core.models.Project.watch_qa_reports_job', return_value=None)
    @patch('conductor.core.models.Project.submit_lava_job', return_value=[123])
    def test_create_build_run_os_tree_hash_none(self, submit_lava_job_mock, watch_qa_reports_mock, get_hash_mock):
        run_name = "imx8mmevk"
        self.build_testplan.build_reason = "Hello world"
        self.build_testplan.build_type = Build.BUILD_TYPE_REGULAR
        self.build_testplan.save()
        create_build_run(self.build_testplan.id, run_name)
        submit_lava_job_mock.assert_not_called()
        watch_qa_reports_mock.assert_not_called()
        get_hash_mock.assert_called()
        assert 1 == get_hash_mock.call_count

    @patch('conductor.core.tasks._get_os_tree_hash', return_value=None)
    @patch('conductor.core.models.Project.watch_qa_reports_job', return_value=None)
    @patch('conductor.core.models.Project.submit_lava_job', return_value=[123])
    def test_create_build_run_skip_qa(self, submit_lava_job_mock, watch_qa_reports_mock, get_hash_mock):
        run_name = "imx8mmevk"
        self.build_testplan.build_reason = "Hello world"
        self.build_testplan.build_type = Build.BUILD_TYPE_REGULAR
        self.build_testplan.skip_qa = True
        self.build_testplan.save()
        create_build_run(self.build_testplan.id, run_name)
        submit_lava_job_mock.assert_not_called()
        watch_qa_reports_mock.assert_not_called()
        get_hash_mock.assert_not_called()

    @patch("django.conf.settings.DEBUG_REPOSITORY_SCRIPTS", True)
    @patch("subprocess.run")
    @patch("os.makedirs")
    def test_create_project_repository(self, makedirs_mock, run_mock):
        repository_path = os.path.join(settings.FIO_REPOSITORY_HOME, self.project.name)
        repository_base = settings.FIO_REPOSITORY_BASE % settings.FIO_DOMAIN
        cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX, "checkout_repository.sh"),
               "-d", repository_path,
               "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
               "-u", "%s/%s/lmp-manifest.git" % (repository_base, self.project.name),
               "-l", settings.FIO_BASE_REMOTE_NAME,
               "-w", settings.FIO_BASE_MANIFEST,
               "-t", self.project.fio_repository_token,
               "-b", self.project.default_branch,
               "-D", settings.FIO_DOMAIN,
               "-f", "True"]
        create_project_repository(self.project.id)
        # at this stage repository should already exist
        # it is created when creating project
        makedirs_mock.assert_not_called()
        run_mock.assert_called_with(cmd, check=True)

    @patch("django.conf.settings.DEBUG_REPOSITORY_SCRIPTS", True)
    @patch("subprocess.run")
    @patch("os.makedirs")
    def test_create_project_repository_meds(self, makedirs_mock, run_mock):
        repository_path = os.path.join(settings.FIO_REPOSITORY_HOME, self.project_meds.name)
        repository_base = settings.FIO_REPOSITORY_BASE % self.project_meds.fio_meds_domain
        cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX, "checkout_repository.sh"),
               "-d", repository_path,
               "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
               "-u", "%s/%s/lmp-manifest.git" % (repository_base, self.project_meds.name),
               "-l", settings.FIO_BASE_REMOTE_NAME,
               "-w", settings.FIO_BASE_MANIFEST,
               "-t", self.project_meds.fio_repository_token,
               "-b", self.project_meds.default_branch,
               "-D", self.project_meds.fio_meds_domain,
               "-f", "True"]
        create_project_repository(self.project_meds.id)
        # at this stage repository should already exist
        # it is created when creating project
        makedirs_mock.assert_not_called()
        run_mock.assert_called_with(cmd, check=True)

    @patch("django.conf.settings.DEBUG_REPOSITORY_SCRIPTS", True)
    @patch("subprocess.run")
    @patch("os.makedirs")
    def test_create_project_repository_partner(self, makedirs_mock, run_mock):
        repository_path = os.path.join(settings.FIO_REPOSITORY_HOME, self.project_partner.name)
        repository_base = settings.FIO_REPOSITORY_BASE % settings.FIO_DOMAIN
        cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX, "checkout_repository.sh"),
               "-d", repository_path,
               "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
               "-u", "%s/%s/lmp-manifest.git" % (repository_base, self.project_partner.name),
               "-l", settings.FIO_BASE_REMOTE_NAME,
               "-w", self.project_partner.fio_lmp_manifest_url,
               "-t", self.project_partner.fio_repository_token,
               "-b", self.project_partner.default_branch,
               "-D", settings.FIO_DOMAIN,
               "-f", "True"]
        create_project_repository(self.project_partner.id)
        # at this stage repository should already exist
        # it is created when creating project
        makedirs_mock.assert_not_called()
        run_mock.assert_called_with(cmd, check=True)

    @patch("django.conf.settings.DEBUG_REPOSITORY_SCRIPTS", True)
    @patch("subprocess.run")
    @patch("os.makedirs")
    def test_create_project(self, makedirs_mock, run_mock):
        project_meds2_name = "testProjectMeds2"
        project_meds2_domain = "meds2.com"
        repository_path = os.path.join(settings.FIO_REPOSITORY_HOME, project_meds2_name)
        repository_base = settings.FIO_REPOSITORY_BASE % project_meds2_domain
        project_meds2 = Project.objects.create(
            name=project_meds2_name,
            secret="webhooksecret",
            lava_backend=self.lavabackend1,
            squad_backend=self.squadbackend1,
            squad_group="squadgroup",
            fio_api_token="fio_api_token_meds2",
            fio_repository_token="fio_repository_token_meds2",
            create_ota_commit=True,
            fio_meds_domain=project_meds2_domain
        )
        cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX, "checkout_repository.sh"),
               "-d", repository_path,
               "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
               "-u", "%s/%s/lmp-manifest.git" % (repository_base, project_meds2.name),
               "-l", settings.FIO_BASE_REMOTE_NAME,
               "-w", settings.FIO_BASE_MANIFEST,
               "-t", project_meds2.fio_repository_token,
               "-b", project_meds2.default_branch,
               "-D", project_meds2_domain,
               "-f", "True"]
        makedirs_mock.assert_called()
        assert 3 == run_mock.call_count
        run_mock.assert_any_call(cmd, check=True)

    @patch("conductor.core.tasks.poll_static_delta_build.apply_async")
    @patch("conductor.core.models.Project.create_static_delta")
    def test_create_static_delta_build(self, create_mock, poll_mock):
        static_delta_json = {"jobserv-url": "https://api.foundries.io/projects/milosz-rpi3/lmp/builds/581/", "web-url": "https://ci.foundries.io/projects/milosz-rpi3/lmp/builds/581"}
        create_mock.return_value = static_delta_json

        create_static_delta_build(self.build.id)
        create_mock.assert_called()
        s_build_id = Build.objects.last().id
        poll_mock.assert_called_with(args=[s_build_id], countdown=120)

    @patch("subprocess.run")
    def test_create_upgrade_commit(self, run_mock):
        repository_path = os.path.join(settings.FIO_REPOSITORY_HOME, self.project.name)
        cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX, "upgrade_commit.sh"),
               "-d", repository_path,
               "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
               "-m", settings.FIO_UPGRADE_ROLLBACK_MESSAGE,
               "-b", self.project.default_branch]

        create_upgrade_commit(self.build.id)
        if not settings.DEBUG_FIO_SUBMIT:
            run_mock.assert_called_with(cmd, capture_output=True, check=True)

    @patch("subprocess.run")
    def test_create_upgrade_commit_test_on_merge_only(self, run_mock):
        repository_path = os.path.join(settings.FIO_REPOSITORY_HOME, self.project.name)
        cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX, "upgrade_commit.sh"),
               "-d", repository_path,
               "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
               "-m", settings.FIO_UPGRADE_ROLLBACK_MESSAGE,
               "-b", self.project.default_branch]

        self.project.test_on_merge_only = True
        self.project.save()
        self.build.is_merge_commit = True
        self.build.save()
        create_upgrade_commit(self.build.id)
        if not settings.DEBUG_FIO_SUBMIT:
            run_mock.assert_called_with(cmd, capture_output=True, check=True)

    @patch("subprocess.run")
    def test_create_upgrade_commit_test_on_merge_only_false(self, run_mock):
        repository_path = os.path.join(settings.FIO_REPOSITORY_HOME, self.project.name)
        cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX, "upgrade_commit.sh"),
               "-d", repository_path,
               "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
               "-m", settings.FIO_UPGRADE_ROLLBACK_MESSAGE,
               "-b", self.project.default_branch]

        self.project.test_on_merge_only = True
        self.project.save()
        self.build.is_merge_commit = False
        self.build.save()
        create_upgrade_commit(self.build.id)
        if not settings.DEBUG_FIO_SUBMIT:
            assert call(cmd, check=True) not in run_mock.mock_calls

    @patch("subprocess.run")
    def test_create_upgrade_commit_rolling(self, run_mock):
        repository_path = os.path.join(settings.FIO_REPOSITORY_HOME, self.project_rolling.name)
        cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX, "upgrade_commit.sh"),
               "-d", repository_path,
               "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
               "-m", settings.FIO_UPGRADE_ROLLBACK_MESSAGE,
               "-b", self.project_rolling.default_branch]

        create_upgrade_commit(self.build_rolling.id)
        if not settings.DEBUG_FIO_SUBMIT:
            run_mock.assert_not_called()

    @patch("conductor.core.tasks.__project_repository_exists", return_value=True)
    @patch("subprocess.run")
    def test_create_upgrade_containers_commit(self, run_mock, exists_mock):
        self.project.create_containers_commit = True
        self.project.compose_app_name = "testapp"
        self.project.compose_app_env_filename = "env"
        self.project.save()
        repository_path = os.path.join(settings.FIO_REPOSITORY_CONTAINERS_HOME, self.project.name)
        cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX, "upgrade_containers_commit.sh"),
               "-d", repository_path,
               "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
               "-m", settings.FIO_UPGRADE_CONTAINER_MESSAGE,
               "-b", self.project.default_branch,
               "-f", f"{self.project.compose_app_name}/{self.project.compose_app_env_filename}"]

        create_upgrade_commit(self.build.id)
        if not settings.DEBUG_FIO_SUBMIT:
            run_mock.assert_called_with(cmd, capture_output=True, check=True)

    @patch("conductor.core.tasks.__project_repository_exists", return_value=True)
    @patch("subprocess.run")
    def test_create_upgrade_containers_commit_no_env_file(self, run_mock, exists_mock):
        self.project.create_containers_commit = True
        self.project.compose_app_name = "testapp"
        self.project.compose_app_env_filename = None
        self.project.save()
        repository_path = os.path.join(settings.FIO_REPOSITORY_CONTAINERS_HOME, self.project.name)
        cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX, "upgrade_containers_commit.sh"),
               "-d", repository_path,
               "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
               "-m", settings.FIO_UPGRADE_CONTAINER_MESSAGE,
               "-b", self.project.default_branch,
               "-f", f"{self.project.compose_app_name}/{self.project.compose_app_env_filename}"]

        create_upgrade_commit(self.build.id)
        if not settings.DEBUG_FIO_SUBMIT:
            run_mock.assert_not_called_with(cmd, check=True)

    @patch("conductor.core.tasks.__project_repository_exists", return_value=True)
    @patch("subprocess.run")
    def test_create_upgrade_containers_commit_no_app_name(self, run_mock, exists_mock):
        self.project.create_containers_commit = True
        self.project.compose_app_name = None
        self.project.compose_app_env_filename = "env"
        self.project.save()
        repository_path = os.path.join(settings.FIO_REPOSITORY_CONTAINERS_HOME, self.project.name)
        cmd = [os.path.join(settings.FIO_REPOSITORY_SCRIPT_PATH_PREFIX, "upgrade_containers_commit.sh"),
               "-d", repository_path,
               "-r", settings.FIO_REPOSITORY_REMOTE_NAME,
               "-m", settings.FIO_UPGRADE_CONTAINER_MESSAGE,
               "-b", self.project.default_branch,
               "-f", f"{self.project.compose_app_name}/{self.project.compose_app_env_filename}"]

        create_upgrade_commit(self.build.id)
        if not settings.DEBUG_FIO_SUBMIT:
            run_mock.assert_not_called_with(cmd, check=True)

    @patch.object(Repo, "remote")
    @patch.object(Repo, "commit")
    @patch("git.Repo.GitCommandWrapperType")
    def test_update_build_reason(self, git_mock, commit_mock, remote_mock):
        remote = MagicMock()
        remote.fetch = MagicMock()
        remote_mock.return_value = remote
        commit = MagicMock()
        commit_message = PropertyMock(return_value="abc")
        type(commit).message = commit_message
        commit_hexsha = PropertyMock(return_value="aaabbbcccddd")
        type(commit).hexsha = commit_hexsha
        commit_mock.return_value = commit

        self.build.commit_id = "aaabbbcccddd"
        self.build.save()
        update_build_reason(self.build.id)
        remote_mock.assert_called()
        remote.fetch.assert_called()
        git_mock.assert_called()
        commit_mock.assert_called()
        commit_message.assert_called()
        self.build.refresh_from_db()
        self.assertEqual(self.build.build_reason, "abc")
        self.assertEqual(self.build.is_merge_commit, False)
        self.assertEqual(self.build.build_type, Build.BUILD_TYPE_REGULAR)

    @patch.object(Repo, "remote")
    @patch.object(Repo, "commit")
    @patch("git.Repo.GitCommandWrapperType")
    def test_update_build_reason_merge_commit(self, git_mock, commit_mock, remote_mock):
        remote = MagicMock()
        remote.fetch = MagicMock()
        remote_mock.return_value = remote
        commit = MagicMock()
        commit_message = PropertyMock(return_value="abc")
        type(commit).message = commit_message
        commit_hexsha = PropertyMock(return_value="aaabbbcccddd")
        type(commit).hexsha = commit_hexsha
        commit_parent1 = MagicMock()
        commit_parent1_hexsha = PropertyMock(return_value="bbbcccdddeee")
        type(commit_parent1).hexsha = commit_parent1_hexsha
        commit_parent2 = MagicMock()
        commit_parent2_hexsha = PropertyMock(return_value="cccdddeeebbb")
        type(commit_parent2).hexsha = commit_parent2_hexsha
        parents = PropertyMock(return_value=[commit_parent1, commit_parent2])
        type(commit).parents = parents
        commit_mock.return_value = commit

        self.build.commit_id = "aaabbbcccddd"
        self.build.save()
        update_build_reason(self.build.id)
        remote_mock.assert_called()
        remote.fetch.assert_called()
        git_mock.assert_called()
        commit_mock.assert_called()
        commit_message.assert_called()
        self.build.refresh_from_db()
        self.assertEqual(self.build.build_reason, "abc")
        self.assertEqual(self.build.is_merge_commit, True)
        self.assertEqual(self.build.build_type, Build.BUILD_TYPE_REGULAR)

    @patch.object(Repo, "remote")
    @patch.object(Repo, "commit")
    @patch("git.Repo.GitCommandWrapperType")
    def test_update_build_reason_upgrade(self, git_mock, commit_mock, remote_mock):
        remote = MagicMock()
        remote.fetch = MagicMock()
        remote_mock.return_value = remote
        commit = MagicMock()
        commit_message = PropertyMock(return_value=settings.FIO_UPGRADE_ROLLBACK_MESSAGE)
        type(commit).message = commit_message
        commit_hexsha = PropertyMock(return_value="aaabbbcccddd")
        type(commit).hexsha = commit_hexsha
        commit_mock.return_value = commit

        self.build.commit_id = "aaabbbcccddd"
        self.build.save()
        update_build_reason(self.build.id)
        remote_mock.assert_called()
        remote.fetch.assert_called()
        git_mock.assert_called()
        commit_mock.assert_called()
        commit_message.assert_called()
        self.build.refresh_from_db()
        self.assertEqual(self.build.build_reason, settings.FIO_UPGRADE_ROLLBACK_MESSAGE)
        self.assertEqual(self.build.build_type, Build.BUILD_TYPE_OTA)

    @patch.object(Repo, "remote")
    @patch.object(Repo, "commit")
    @patch("git.Repo.GitCommandWrapperType")
    def test_update_build_reason_missing_commit(self, git_mock, commit_mock, remote_mock):
        # commit is missing from lmp-manifest and meta-sub repositories
        remote = MagicMock()
        remote.fetch = MagicMock()
        remote_mock.return_value = remote
        def commit(rev):
            if rev == "HEAD":
                return_mock = MagicMock()
                commit_hexsha = PropertyMock(return_value="aaabbbcccddd")
                type(return_mock).hexsha = commit_hexsha
                return return_mock
            raise ValueError
        commit_mock.side_effect = commit

        self.build.commit_id = "aaabbbcccddd"
        self.build.save()
        update_build_reason(self.build.id)
        remote_mock.assert_called()
        remote.fetch.assert_called()
        git_mock.assert_called()
        commit_mock.assert_called()
        self.build.refresh_from_db()
        self.assertEqual(self.build.build_reason, "Trigerred from unknown source")
        self.assertEqual(self.build.build_type, Build.BUILD_TYPE_REGULAR)

    @patch("conductor.core.tasks.create_upgrade_commit.delay")
    @patch("requests.Session.get")
    @patch.object(Repo, "remote")
    @patch.object(Repo, "commit")
    @patch("git.Repo.GitCommandWrapperType")
    def test_update_commit_id(self, git_mock, commit_mock, remote_mock, get_mock, upgrade_mock):
        remote = MagicMock()
        remote.fetch = MagicMock()
        remote_mock.return_value = remote
        commit = MagicMock()
        commit_message = PropertyMock(return_value="abc")
        type(commit).message = commit_message
        commit_hexsha = PropertyMock(return_value="aaabbbcccddd")
        type(commit).hexsha = commit_hexsha
        commit_mock.return_value = commit

        request = MagicMock()
        type(request).status_code = PropertyMock(return_value=200)
        request.json = MagicMock(return_value=RUNDEF_JSON)
        get_mock.return_value=request

        update_build_commit_id(self.build.id, "https://foo.bar.com")
        remote_mock.assert_called()
        remote.fetch.assert_called()
        git_mock.assert_called()
        commit_mock.assert_called()
        commit_message.assert_called()
        self.build.refresh_from_db()
        self.assertEqual(self.build.commit_id, "8d52c43b2ee7f15ba6300db4e37f31db80e9cc06")
        self.assertEqual(self.build.build_reason, "abc")
        self.assertEqual(self.build.build_type, Build.BUILD_TYPE_REGULAR)
        upgrade_mock.assert_called()

    @patch("conductor.core.tasks.create_static_delta_build.delay")
    @patch("conductor.core.tasks.create_upgrade_commit.delay")
    @patch("requests.Session.get")
    @patch.object(Repo, "remote")
    @patch.object(Repo, "commit")
    @patch("git.Repo.GitCommandWrapperType")
    def test_update_commit_id_ota_build(self, git_mock, commit_mock, remote_mock, get_mock, upgrade_mock, static_delta_mock):
        remote = MagicMock()
        remote.fetch = MagicMock()
        remote_mock.return_value = remote
        commit = MagicMock()
        commit_message = PropertyMock(return_value=settings.FIO_UPGRADE_ROLLBACK_MESSAGE)
        type(commit).message = commit_message
        commit_hexsha = PropertyMock(return_value="aaabbbcccddd")
        type(commit).hexsha = commit_hexsha
        commit_mock.return_value = commit

        request = MagicMock()
        type(request).status_code = PropertyMock(return_value=200)
        request.json = MagicMock(return_value=RUNDEF_JSON)
        get_mock.return_value=request

        update_build_commit_id(self.build.id, "https://foo.bar.com")
        remote_mock.assert_called()
        remote.fetch.assert_called()
        git_mock.assert_called()
        commit_mock.assert_called()
        commit_message.assert_called()
        self.build.refresh_from_db()
        self.assertEqual(self.build.commit_id, "8d52c43b2ee7f15ba6300db4e37f31db80e9cc06")
        self.assertEqual(self.build.build_reason, settings.FIO_UPGRADE_ROLLBACK_MESSAGE)
        self.assertEqual(self.build.build_type, Build.BUILD_TYPE_OTA)
        upgrade_mock.assert_not_called()
        static_delta_mock.assert_called()

    @patch("conductor.core.tasks.create_upgrade_commit.delay")
    @patch("requests.Session.get")
    @patch.object(Repo, "remote")
    @patch.object(Repo, "commit")
    def test_update_commit_id_no_access(self, commit_mock, remote_mock, get_mock, upgrade_mock):
        remote = MagicMock()
        remote.pull = MagicMock()
        remote_mock.return_value = remote
        commit = MagicMock()
        commit_message = PropertyMock(return_value="abc")
        type(commit).message = commit_message
        commit_mock.return_value = commit

        request = MagicMock()
        type(request).status_code = PropertyMock(return_value=404)
        request.json = MagicMock(return_value=RUNDEF_JSON)
        get_mock.return_value=request

        update_build_commit_id(self.build.id, "https://foo.bar.com")
        remote_mock.assert_not_called()
        remote.pull.assert_not_called()
        commit_mock.assert_not_called()
        commit_message.assert_not_called()
        self.build.refresh_from_db()
        self.assertEqual(self.build.commit_id, None)
        self.assertEqual(self.build.build_reason, None)
        self.assertEqual(self.build.build_type, Build.BUILD_TYPE_REGULAR)
        upgrade_mock.assert_not_called()



    @patch('requests.put')
    @patch('requests.get')
    def test_tag_build_runs(self, get_mock, put_mock):
        targets_json = {
          "signatures": [
            {
              "keyid": "c567cbb9576c9cb2d94554c9bdf230fe9fc84f43bfc773a74d3451cc05716171",
              "method": "rsassa-pss-sha256",
              "sig": "fmkTP2o9D+lATkmhEoBBH5tomhvYkXTtbe7z13wEQW1VkBdStlYwvciIfxPElh2wVWLUUofmoxar/91blEmjhHH3Lnup5hXwbTRM1NQb8LjLxrjOyk7YAewNPd7GahyVI6aUo2npjTiC7X3n0OA4eRbBqIVJ0nCojSAwWREFcFZYNVVCoGIkOz4F/eFAPONIp0r+e7Hd+0uUrKHY4RvNvRMD81uSG91vjB/ngTE0++0YOgqo54Xf0uHeBnDLpw8YjBqssmV+BhigIKHmOmBbMp2M25BKyV+oCABLmpySL2Fgp4b2HHw405uIGhn4E2sz2Cw4dtuoa/qBA7CWy5xelw=="
            }
          ],
          "signed": {
            "_type": "Targets",
            "expires": "2022-03-22T12:52:29Z",
            "version": 1197,
            "targets": {
              "am64xx-evm-lmp-268": {
                "hashes": {
                  "sha256": "16c74d7813f9cda8164e7eb31d718db11615e90f63a8fab880b97512be455b36"
                },
                "length": 0,
                "custom": {
                  "cliUploaded": False,
                  "name": "am64xx-evm-lmp",
                  "version": "268",
                  "hardwareIds": [
                    "am64xx-evm"
                  ],
                  "targetFormat": "OSTREE",
                  "uri": "https://ci.foundries.io/projects/milosz-rpi3/lmp/builds/268",
                  "createdAt": "2022-02-14T19:44:56Z",
                  "updatedAt": "2022-02-14T19:44:56Z",
                  "lmp-manifest-sha": "97a9416598fe20b46b36448527d9832f181b038d",
                  "arch": "aarch64",
                  "image-file": "lmp-factory-image-am64xx-evm.wic.gz",
                  "meta-subscriber-overrides-sha": "6bfeb94ef4bfffd1afe4b58187b1c81a5e39cc12",
                  "tags": [
                    "master"
                  ]
                }
              }
            }
          }
        }
        get_response = MagicMock()
        get_response.json = MagicMock(return_value=targets_json)
        get_mock.return_value = get_response

        self.project.testing_tag = "testing1"
        self.project.privkey = PEM_PRIV_KEY
        self.project.keyid = "abcdefghi123456789"
        self.project.apply_testing_tag_on_callback = True
        self.project.save()
        tag_build_runs(self.old_previous_build.pk)
        bt = BuildTag.objects.filter(builds=self.old_previous_build)
        self.assertEqual(len(bt), 1)
        if not settings.DEBUG_FIO_SUBMIT:
            get_mock.assert_called()
            put_mock.assert_called()
        tag_build_runs(self.previous_build.pk)
        project_buildtag = BuildTag.objects.get(name=self.project.testing_tag)
        tagged_builds = Build.objects.filter(buildtag=project_buildtag)
        self.assertEqual(len(tagged_builds), 2)
        if not settings.DEBUG_FIO_SUBMIT:
            get_mock.assert_called()
            put_mock.assert_called()
        tag_build_runs(self.build.pk)
        tagged_builds = Build.objects.filter(buildtag=project_buildtag)
        self.assertEqual(len(tagged_builds), 2)

    @patch('requests.put')
    @patch('requests.get')
    def test_tag_build_runs_ed25519(self, get_mock, put_mock):
        targets_json = {
          "signatures": [
            {
              "keyid": "c567cbb9576c9cb2d94554c9bdf230fe9fc84f43bfc773a74d3451cc05716171",
              "method": "rsassa-pss-sha256",
              "sig": "fmkTP2o9D+lATkmhEoBBH5tomhvYkXTtbe7z13wEQW1VkBdStlYwvciIfxPElh2wVWLUUofmoxar/91blEmjhHH3Lnup5hXwbTRM1NQb8LjLxrjOyk7YAewNPd7GahyVI6aUo2npjTiC7X3n0OA4eRbBqIVJ0nCojSAwWREFcFZYNVVCoGIkOz4F/eFAPONIp0r+e7Hd+0uUrKHY4RvNvRMD81uSG91vjB/ngTE0++0YOgqo54Xf0uHeBnDLpw8YjBqssmV+BhigIKHmOmBbMp2M25BKyV+oCABLmpySL2Fgp4b2HHw405uIGhn4E2sz2Cw4dtuoa/qBA7CWy5xelw=="
            }
          ],
          "signed": {
            "_type": "Targets",
            "expires": "2022-03-22T12:52:29Z",
            "version": 1197,
            "targets": {
              "am64xx-evm-lmp-268": {
                "hashes": {
                  "sha256": "16c74d7813f9cda8164e7eb31d718db11615e90f63a8fab880b97512be455b36"
                },
                "length": 0,
                "custom": {
                  "cliUploaded": False,
                  "name": "am64xx-evm-lmp",
                  "version": "268",
                  "hardwareIds": [
                    "am64xx-evm"
                  ],
                  "targetFormat": "OSTREE",
                  "uri": "https://ci.foundries.io/projects/milosz-rpi3/lmp/builds/268",
                  "createdAt": "2022-02-14T19:44:56Z",
                  "updatedAt": "2022-02-14T19:44:56Z",
                  "lmp-manifest-sha": "97a9416598fe20b46b36448527d9832f181b038d",
                  "arch": "aarch64",
                  "image-file": "lmp-factory-image-am64xx-evm.wic.gz",
                  "meta-subscriber-overrides-sha": "6bfeb94ef4bfffd1afe4b58187b1c81a5e39cc12",
                  "tags": [
                    "master"
                  ]
                }
              }
            }
          }
        }
        get_response = MagicMock()
        get_response.json = MagicMock(return_value=targets_json)
        get_mock.return_value = get_response

        self.project.testing_tag = "testing1"
        self.project.privkey = PEM_PRIV_KEY_ED25519
        self.project.keyid = "abcdefghi123456789"
        self.project.apply_testing_tag_on_callback = True
        self.project.save()
        tag_build_runs(self.old_previous_build.pk)
        bt = BuildTag.objects.filter(builds=self.old_previous_build)
        self.assertEqual(len(bt), 1)
        if not settings.DEBUG_FIO_SUBMIT:
            get_mock.assert_called()
            put_mock.assert_called()
        tag_build_runs(self.previous_build.pk)
        project_buildtag = BuildTag.objects.get(name=self.project.testing_tag)
        tagged_builds = Build.objects.filter(buildtag=project_buildtag)
        self.assertEqual(len(tagged_builds), 2)
        if not settings.DEBUG_FIO_SUBMIT:
            get_mock.assert_called()
            put_mock.assert_called()
        tag_build_runs(self.build.pk)
        tagged_builds = Build.objects.filter(buildtag=project_buildtag)
        self.assertEqual(len(tagged_builds), 2)

    @patch('requests.put')
    @patch('requests.get')
    def test_tag_build_runs_first_build_only(self, get_mock, put_mock):
        targets_json = {
          "signatures": [
            {
              "keyid": "c567cbb9576c9cb2d94554c9bdf230fe9fc84f43bfc773a74d3451cc05716171",
              "method": "rsassa-pss-sha256",
              "sig": "fmkTP2o9D+lATkmhEoBBH5tomhvYkXTtbe7z13wEQW1VkBdStlYwvciIfxPElh2wVWLUUofmoxar/91blEmjhHH3Lnup5hXwbTRM1NQb8LjLxrjOyk7YAewNPd7GahyVI6aUo2npjTiC7X3n0OA4eRbBqIVJ0nCojSAwWREFcFZYNVVCoGIkOz4F/eFAPONIp0r+e7Hd+0uUrKHY4RvNvRMD81uSG91vjB/ngTE0++0YOgqo54Xf0uHeBnDLpw8YjBqssmV+BhigIKHmOmBbMp2M25BKyV+oCABLmpySL2Fgp4b2HHw405uIGhn4E2sz2Cw4dtuoa/qBA7CWy5xelw=="
            }
          ],
          "signed": {
            "_type": "Targets",
            "expires": "2022-03-22T12:52:29Z",
            "version": 1197,
            "targets": {
              "am64xx-evm-lmp-268": {
                "hashes": {
                  "sha256": "16c74d7813f9cda8164e7eb31d718db11615e90f63a8fab880b97512be455b36"
                },
                "length": 0,
                "custom": {
                  "cliUploaded": False,
                  "name": "am64xx-evm-lmp",
                  "version": "268",
                  "hardwareIds": [
                    "am64xx-evm"
                  ],
                  "targetFormat": "OSTREE",
                  "uri": "https://ci.foundries.io/projects/milosz-rpi3/lmp/builds/268",
                  "createdAt": "2022-02-14T19:44:56Z",
                  "updatedAt": "2022-02-14T19:44:56Z",
                  "lmp-manifest-sha": "97a9416598fe20b46b36448527d9832f181b038d",
                  "arch": "aarch64",
                  "image-file": "lmp-factory-image-am64xx-evm.wic.gz",
                  "meta-subscriber-overrides-sha": "6bfeb94ef4bfffd1afe4b58187b1c81a5e39cc12",
                  "tags": [
                    "master"
                  ]
                }
              }
            }
          }
        }
        get_response = MagicMock()
        get_response.json = MagicMock(return_value=targets_json)
        get_mock.return_value = get_response

        self.project.testing_tag = "testing1"
        self.project.privkey = PEM_PRIV_KEY_ED25519
        self.project.keyid = "abcdefghi123456789"
        self.project.apply_testing_tag_on_callback = True
        self.project.apply_tag_to_first_build_only = True
        self.project.save()
        self.build.build_reason = "FooBar"
        self.build.save()
        tag_build_runs(self.old_previous_build.pk)
        bt = BuildTag.objects.filter(builds=self.old_previous_build)
        self.assertEqual(len(bt), 1)
        if not settings.DEBUG_FIO_SUBMIT:
            get_mock.assert_called()
            put_mock.assert_called()
        tag_build_runs(self.previous_build.pk)
        project_buildtag = BuildTag.objects.get(name=self.project.testing_tag)
        tagged_builds = Build.objects.filter(buildtag=project_buildtag)
        self.assertEqual(len(tagged_builds), 2)
        if not settings.DEBUG_FIO_SUBMIT:
            get_mock.assert_called()
            put_mock.assert_called()
        tag_build_runs(self.build.pk)
        tagged_builds = Build.objects.filter(buildtag=project_buildtag)
        self.assertEqual(len(tagged_builds), 2)

    def test_tag_build_runs_no_build(self):
        ret = tag_build_runs(99999)
        self.assertEqual(ret, None)

    def test_tag_build_runs_dont_apply(self):
        self.project.apply_testing_tag_on_callback = False
        self.project.save()
        ret = tag_build_runs(self.build.pk)
        self.assertEqual(ret, None)

    def test_tag_build_runs_no_project_tag(self):
        self.project.testing_tag = None
        self.project.save()
        ret = tag_build_runs(self.build.pk)
        self.assertEqual(ret, None)

    def test_tag_build_runs_apply_on_first_ota_build(self):
        self.project.testing_tag = "testing"
        self.project.apply_tag_to_first_build_only = True
        self.project.save()
        self.build.build_reason = settings.FIO_UPGRADE_ROLLBACK_MESSAGE
        self.build.save()
        ret = tag_build_runs(self.build.pk)
        self.assertEqual(ret, None)

    def test_schedule_static_delta_no_build(self):
        ret = schedule_static_delta(999)
        self.assertEqual(ret, None)

    def test_schedule_static_delta_no_from(self):
        ret = schedule_static_delta(self.build.id)
        self.assertEqual(ret, None)

    def test_schedule_static_delta_skip_qa(self):
        self.previous_build.skip_qa = True
        self.previous_build.save()
        self.build.static_from = self.previous_build
        self.build.save()
        ret = schedule_static_delta(self.build.id)
        self.assertEqual(ret, None)

    @patch('conductor.core.tasks._get_os_tree_hash', return_value="someHash1")
    @patch('conductor.core.models.SQUADBackend.update_testjob')
    @patch('conductor.core.models.Project.watch_qa_reports_job')
    @patch('conductor.core.models.Project.submit_lava_job', return_value=[123])
    @patch('conductor.core.tasks.update_build_reason')
    def test_schedule_static_delta(self, update_build_reason_mock, submit_lava_job_mock, watch_qa_reports_mock, update_testjob_mock, get_hash_mock):

        response_mock = MagicMock()
        response_mock.status_code = 201
        response_mock.text = "321"
        watch_qa_reports_mock.return_value = response_mock
        #run_name = "imx8mmevk"
        #self.build_testplan.build_reason = "Hello world"
        #self.build_testplan.build_type = Build.BUILD_TYPE_REGULAR
        #self.build_testplan.save()

        schedule_static_delta(self.build_testplan_static.pk)

        #create_build_run(self.build_testplan.id, run_name)
        #update_build_reason_mock.assert_not_called()
        submit_lava_job_mock.assert_called()
        watch_qa_reports_mock.assert_called()
        update_testjob_mock.assert_called()
        assert 1 == submit_lava_job_mock.call_count
        get_hash_mock.assert_called()
        assert 1 == get_hash_mock.call_count

    @patch('conductor.core.tasks.poll_static_delta_build.apply_async')
    @patch('conductor.core.models.Project.ci_build_details')
    def test_poll_static_delta_running(self, ci_mock, poll_mock):
        build_details_json = {"status": "RUNNING"}
        ci_mock.return_value = build_details_json
        poll_static_delta_build(self.build.id)
        poll_mock.assert_called()

    @patch('conductor.core.tasks.schedule_static_delta')
    @patch('conductor.core.tasks.poll_static_delta_build.apply_async')
    @patch('conductor.core.models.Project.ci_build_details')
    def test_poll_static_delta_passed(self, ci_mock, poll_mock, schedule_mock):
        build_details_json = {"status": "PASSED"}
        ci_mock.return_value = build_details_json
        poll_static_delta_build(self.build.id)
        poll_mock.assert_not_called()
        schedule_mock.assert_called()

    @patch('conductor.core.tasks.schedule_static_delta')
    @patch('conductor.core.tasks.poll_static_delta_build.apply_async')
    @patch('conductor.core.models.Project.ci_build_details')
    def test_poll_static_delta_failed(self, ci_mock, poll_mock, schedule_mock):
        build_details_json = {"status": "FAILED"}
        ci_mock.return_value = build_details_json
        ret_val = poll_static_delta_build(self.build.id)
        poll_mock.assert_not_called()
        schedule_mock.assert_not_called()
        self.assertEqual(None, ret_val)

    @patch('conductor.core.tasks.create_build_run.si')
    @patch('conductor.core.tasks.tag_build_runs.si')
    @patch('conductor.core.tasks.update_build_commit_id.si')
    def test_schedule_project_test_round(self, update_mock, tag_mock, create_mock):
        schedule_project_test_round(self.build.id)
        update_mock.assert_called()
        tag_mock.assert_called()
        create_mock.assert_called()

    @patch('conductor.core.tasks.create_build_run.si')
    @patch('conductor.core.tasks.tag_build_runs.si')
    @patch('conductor.core.tasks.update_build_commit_id.si')
    def test_schedule_project_test_round_no_build(self, update_mock, tag_mock, create_mock):
        schedule_project_test_round(999)
        update_mock.assert_not_called()
        tag_mock.assert_not_called()
        create_mock.assert_not_called()
