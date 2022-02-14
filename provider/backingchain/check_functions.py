import logging
import re

from avocado.utils import process
from virttest import utils_misc
from virttest import libvirt_storage

LOG = logging.getLogger('avocado.backingchain.checkfunction')


class Checkfunction(object):
    """
        Prepare data for blockcommand test

        :param test: Test object
        :param vm:  A libvirt_vm.VM class instance.
        :param params: Dict with the test parameters.
    """

    def __init__(self, test, vm, params):
        self.test = test
        self.vm = vm
        self.params = params

    def check_block_operation_result(self, vmxml, blockcommand,
                                     target_dev, bc_chain):
        """
        Run specific check backing chain function.

        :param vmxml: vmxml obj of vm
        :param blockcommand: blockpull, blockcommit..
        :param target_dev: dev of target disk, different disks could have
        different chain
        :param bc_chain: original backing chain info as a list of source files
        """
        check_func = self.params.get('check_func', '')
        check_bc_func_name = 'self.check_bc_%s' % check_func
        check_bc = eval(check_bc_func_name)
        # Run specific check backing chain function
        if not check_bc(blockcommand, vmxml, target_dev, bc_chain):
            self.test.fail('Backing chain check after %s failed' % blockcommand)

    def check_bc_base_top(self, command, vmxml, dev, bc_chain):
        """
        Check backing chain info after blockpull/commit
        from base to top(or top to base)

        :param command: blockpull, blockcommit..
        :param vmxml: vmxml obj of vm
        :param dev: dev of target disk
        :param bc_chain: original backing chain info as a list of source files
        :return: True if check passed, False if failed
        """
        LOG.info('Check backing chain after %s', command)
        disk = vmxml.get_disk_all()[dev]
        disk_type = disk.get('type')
        disk_source = disk.find('source')
        if disk_type == 'file':
            src_path = disk_source.get('file')
        elif disk_type == 'block':
            src_path = disk_source.get('dev')
        elif disk_type == 'network':
            src_path = '{}://{}/{}'.format(disk_source.get('protocol'),
                                           disk_source.find('host').get('name'),
                                           disk_source.get('name'))
        else:
            LOG.error('Unknown disk type: %s', disk_type)
            return False
        LOG.debug('Current source file: %s', src_path)
        if command == 'blockpull':
            index = 0
        elif command == 'blockcommit':
            index = -1
        else:
            LOG.error('Unsupported command: %s', command)
            return False
        if src_path != bc_chain[index]:
            LOG.error('Expect source file to be %s, but got %s', bc_chain[index], src_path)
            return False
        bs = disk.find('backingStore')
        LOG.debug('Current backing store: %s', bs)
        if bs and bs.find('source') is not None:
            LOG.error('Backing store of disk %s, should be empty', dev)
            return False

        LOG.info('Backing chain check PASS.')
        return True

    def check_backingchain(self, img_list):
        """
        Check backing chain info through qemu-img info

        :param img_list: expected backingchain list
        :return: bool, meets expectation or not
        """
        # Get actual backingchain list
        qemu_img_cmd = 'qemu-img info --backing-chain %s' % img_list[0]
        if libvirt_storage.check_qemu_image_lock_support():
            qemu_img_cmd += " -U"
        img_info = process.run(qemu_img_cmd, verbose=True, shell=True).stdout_text
        # Set check pattern
        pattern = ''
        chain_length = len(img_list)
        for i in range(chain_length):
            pattern += 'image: ' + img_list[i]
            if i + 1 < chain_length:
                pattern += '.*backing file: ' + img_list[i + 1]
            pattern += '.*'
        LOG.debug('The pattern to match the current backing chain is:%s'
                  % pattern)
        # compare list
        exist = re.search(pattern, img_info, re.DOTALL)
        if not exist:
            self.test.fail('qemu-img info output of backing chain '
                           'is not correct: %s' % img_info)
        return exist

    def check_image_size(self, image_path):
        """
        Check image size with qemu-img command.
        :param image_path: the path of image.
        """
        resize_value = self.params.get('new_size')
        image_format = self.params.get('driver_type')

        # Format expected image size
        # Although kb should not be used, libvirt/virsh will accept it and
        # consider it as a 1000 bytes, which caused issues for qed & qcow2
        # since they expect a value evenly divisible by 512 (hence bz 1002813).
        expected_size = 0
        if "kb" in resize_value:
            value = int(resize_value[:-2])
            if image_format in ["qed", "qcow2"]:
                # qcow2 and qed want a VIR_ROUND_UP value based on 512 byte
                # sectors - hence this less than visually appealing formula
                expected_size = (((value * 1000) + 512 - 1) // 512) * 512
            else:
                # Raw images...
                # Ugh - there's some rather ugly looking math when kb
                # (or mb, gb, tb, etc.) are used as the scale for the
                # value to create an image. The blockresize for the
                # running VM uses a qemu json call which differs from
                # qemu-img would do - resulting in (to say the least)
                # awkward sizes. We'll just have to make sure we don't
                # deviates more than a sector.
                expected_size = value * 1000
        elif "kib" in resize_value:
            value = int(resize_value[:-3])
            expected_size = value * 1024
        elif resize_value[-1] in "b":
            expected_size = int(resize_value[:-1])
        elif resize_value[-1] in "k":
            value = int(resize_value[:-1])
            expected_size = value * 1024
        elif resize_value[-1] == "m":
            value = int(resize_value[:-1])
            expected_size = value * 1024 * 1024
        elif resize_value[-1] == "g":
            value = int(resize_value[:-1])
            expected_size = value * 1024 * 1024 * 1024
            cmd = "qemu-img info %s" % image_path
            if libvirt_storage.check_qemu_image_lock_support():
                cmd += " -U"
            ret = process.run(cmd, allow_output_check='combined', shell=True)
            status, output = (ret.exit_status, ret.stdout_text.strip())
            value_return_by_qemu_img = re.search \
                (r'virtual size:\s+(\d+(\.\d+)?)+\s?G', output).group(1)
            if value != int(float(value_return_by_qemu_img)):
                self.test.fail("initial image size in config is not "
                               "equals to value returned by qemu-img info")
        else:
            self.test.error("Unknown scale value")

        # Get current image size
        image_info = utils_misc.get_image_info(image_path)
        actual_size = int(image_info['vsize'])

        LOG.info("The expected block size is %s bytes, "
                 "the actual block size is %s bytes",
                 expected_size, actual_size)

        # Check the expected size and actualsize
        # See comment above regarding Raw images
        if image_format == "raw" and resize_value[-2] in "kb":
            if abs(int(actual_size) - int(expected_size)) > 512:
                self.test.fail("New raw blocksize set by blockresize do "
                               "not match the expected value")
        else:
            if int(actual_size) != int(expected_size):
                self.test.fail("New blocksize set by blockresize is "
                               "different from actual size from "
                               "'qemu-img info'")
