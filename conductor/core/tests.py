# Copyright 2021 Foundries.io
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from django.test import TestCase
from unittest.mock import patch, MagicMock, PropertyMock

from conductor.core.models import Project, Build, Run, LAVADeviceType, LAVADevice, LAVAJob
from conductor.core.tasks import create_build_run, create_ota_job, device_pdu_action


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


class ProjectTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="testProject1",
            secret="webhooksecret",
            lava_url="http://lava.example.com/api/v0.2/",
            lava_api_token="lavatoken",
        )

    @patch('requests.post')
    def test_submit_lava_job(self, post_mock):
        definition = "lava test definition"
        response_mock = MagicMock()
        response_mock.status_code = 201
        response_mock.json.return_value = {'job_ids': ['123']}
        post_mock.return_value = response_mock

        ret_list = self.project.submit_lava_job(definition)
        post_mock.assert_called()
        self.assertEqual(ret_list, ['123'])


class TaskTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="testProject1",
            secret="webhooksecret",
            lava_url="http://lava.example.com/api/v0.2/",
            lava_api_token="lavatoken",
        )
        self.previous_build = Build.objects.create(
            url="https://example.com/build/1/",
            project=self.project,
            build_id="1"
        )
        self.previous_build_run_1 = Run.objects.create(
            build=self.previous_build,
            device_type="device-type-1",
            ostree_hash="previousHash",
            run_name="device-type-1"
        )
        self.build = Build.objects.create(
            url="https://example.com/build/2/",
            project=self.project,
            build_id="2"
        )
        self.device_type1 = LAVADeviceType.objects.create(
            name="device-type-1",
            net_interface="eth0",
            project=self.project,
        )
        self.lava_device1 = LAVADevice.objects.create(
            device_type = self.device_type1,
            name = "device-type-1-1",
            project = self.project
        )

    @patch('conductor.core.tasks._get_os_tree_hash', return_value="someHash1")
    @patch('conductor.core.models.Project.submit_lava_job', return_value=[123])
    @patch('conductor.core.tasks.create_ota_job')
    def test_create_build_run(self, ota_job_mock, submit_lava_job_mock, get_hash_mock):
        run_name = "device-type-1"
        run_url = f"{self.build.url}runs/{run_name}/"
        create_build_run(self.build.id, run_url, run_name)
        submit_lava_job_mock.assert_called_once()
        get_hash_mock.assert_called_once()
        ota_job_mock.assert_called_once()

    @patch('conductor.core.tasks._get_os_tree_hash', return_value="someHash1")
    @patch('conductor.core.models.Project.submit_lava_job', return_value=[123])
    @patch('conductor.core.tasks.create_ota_job')
    def test_create_build_run_ota(self, ota_job_mock, submit_lava_job_mock, get_hash_mock):
        run_name = "device-type-1"
        run_url = f"{self.build.url}runs/{run_name}/"
        create_build_run(self.build.id, run_url, run_name, LAVAJob.JOB_OTA)
        submit_lava_job_mock.assert_called_once()
        get_hash_mock.assert_called_once()
        ota_job_mock.assert_not_called()

    @patch('conductor.core.tasks.create_build_run')
    def test_create_ota_job(self, create_build_run_mock):
        run_name = "device-type-1"
        previous_run_url = f"{self.previous_build.url}runs/{run_name}/"
        run_url = f"{self.build.url}runs/{run_name}/"
        create_ota_job(self.build.id, run_url, run_name)
        create_build_run_mock.assert_called_with(
            self.previous_build.id,
            previous_run_url,
            run_name,
            lava_job_type=LAVAJob.JOB_OTA
        )

    #def test_update_build_commit_id(self):
    @patch("requests.get")
    @patch("conductor.core.models.PDUAgent.save")
    def test_device_pdu_action_on(self, save_mock, get_mock):
        response_mock = MagicMock()
        response_mock.status_code = 200
        response_mock.text = DEVICE_DICT
        get_mock.return_value = response_mock
        device_pdu_action(self.lava_device1.pk)
        save_mock.assert_called()

    @patch("requests.get")
    @patch("conductor.core.models.PDUAgent.save")
    def test_device_pdu_action_off(self, save_mock, get_mock):
        response_mock = MagicMock()
        response_mock.status_code = 200
        response_mock.text = DEVICE_DICT
        get_mock.return_value = response_mock
        device_pdu_action(self.lava_device1.pk, power_on=False)
        save_mock.assert_called()
