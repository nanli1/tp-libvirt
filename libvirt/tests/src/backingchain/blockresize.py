import logging
import os

from avocado.utils import process

from virttest import virsh
from virttest.libvirt_xml import vm_xml
from virttest.utils_libvirt import libvirt_disk
from virttest.utils_test import libvirt

from provider.backingchain import blockcommand_base
from provider.backingchain import check_functions


def run(test, params, env):
    """
    Test blockresize for raw type device which has backing chain element.

    1) Prepare an running guest which has a raw image.
    2) Resize the block device using GB and KB.
    3) Check size.
    """

    def setup_raw_disk_blockresize():
        """
        Prepare raw disk and create snapshots.
        """
        # Create raw type image
        image_path, device = test_obj.tmp_dir + '/blockresize_test', 'vdd'
        cmd = "qemu-img create -f %s %s %s" % ('raw', image_path,
                                               '500K')
        process.run(cmd, allow_output_check='combined', shell=True)
        test_obj.new_image_path = image_path
        # attach new disk
        virsh.attach_disk(vm.name, source=image_path, target=device,
                          extra=" --subdriver %s" % "raw", debug=True)
        test_obj.new_dev = device
        # create snap chain
        test_obj.prepare_snapshot()

    def test_raw_disk_blockresize():
        """
        Do blockresize for device which has backing chain element
        """
        new_size = params.get('new_size')
        result = virsh.blockresize(vm_name, test_obj.snap_path_list[-1],
                                   new_size, debug=True)
        libvirt.check_exit_status(result)
        check_obj.check_image_size(test_obj.snap_path_list[-1])

    def teardown_raw_disk_blockresize():
        """
        Clean env and resize with origin size.
        """
        # clean new disk file
        logging.info('Start cleaning up.')
        for ss in test_obj.snap_name_list:
            virsh.snapshot_delete(vm_name, '%s --metadata' % ss, debug=True)
        for sp in test_obj.snap_path_list:
            process.run('rm -rf %s' % sp)
        # clean first disk snap file
        image_path = os.path.dirname(original_disk_source)
        for sf in os.listdir(image_path):
            if 'snap' in sf:
                process.run('rm -rf %s/%s' % (image_path, sf))
        # detach disk
        virsh.detach_disk(vm_name, target=test_obj.new_dev, debug=True)
        process.run('rm -rf %s' % test_obj.new_image_path)

    # Process cartesian parameters
    vm_name = params.get("main_vm")
    vm = env.get_vm(vm_name)
    case_name = params.get('case_name', '')
    # Get vm xml
    vmxml = vm_xml.VMXML.new_from_inactive_dumpxml(vm_name)
    bkxml = vmxml.copy()
    original_disk_source = libvirt_disk.get_first_disk_source(vm)
    # Create object
    test_obj = blockcommand_base.BlockCommand(test, vm, params)
    check_obj = check_functions.Checkfunction(test, vm, params)

    # MAIN TEST CODE ###
    run_test = eval("test_%s" % case_name)
    setup_test = eval("setup_%s" % case_name)
    teardown_test = eval("teardown_%s" % case_name)

    try:
        # Execute test
        setup_test()
        run_test()

    finally:
        teardown_test()
        bkxml.sync()
