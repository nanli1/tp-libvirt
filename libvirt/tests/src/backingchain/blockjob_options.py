import logging
import os
import re
import time

LOG = logging.getLogger('avocado.' + __name__)

from avocado.utils import process

from virttest import virsh
from virttest.libvirt_xml import vm_xml

from provider.backingchain import blockcommand_base
from provider.backingchain import check_functions


def run(test, params, env):
    """
    Test blockjob operation

    1) Prepare a running guest.
    2) Do blockcopy.
    3) Do blockjob with raw, sync or other option.
    """
    def setup_blockjob_raw():
        """
        Prepare running domain and do blockcopy
        """
        if not vm.is_alive():
            vm.start()

        if os.path.exists(tmp_copy_path):
            process.run('rm -rf %s' % tmp_copy_path)

        cmd = "blockcopy %s vda %s --wait --verbose --transient-job " \
              "--bandwidth 200 " % (vm_name, tmp_copy_path)
        virsh_session = virsh.VirshSession(virsh_exec=virsh.VIRSH_EXEC,
                                           auto_close=True)
        virsh_session.sendline(cmd)

    def test_blockjob_raw():
        """
        Do blockjob with raw, sync or other option.
        """
        options = params.get('option_value', '')
        res_1 = virsh.blockjob(vm_name, 'vda', options=options, debug=True,
                               ignore_status=False)
        cur1 = check_obj.check_blockjob_raw_result(res_1)
        time.sleep(1)
        res_2 = virsh.blockjob(vm_name, 'vda', options=' --raw', debug=True,
                                  ignore_status=False)
        cur2 = check_obj.check_blockjob_raw_result(res_2)
        LOG.debug('cur1 is %s , cur2 is %s', cur1, cur2)
        if cur1 >= cur2:
            test.fail('Two times cur value is not changed according'
                      ' to the progress of blockcopy.')

    def teardown_blockjob_raw():
        """
        After blockcopy, abort job and clean file
        """
        # Abort job and check abort success.
        for i in range(100):
            time.sleep(1)
            ret = virsh.blockjob(vm_name, 'vda', "--info")
            if ret.stderr.count("Block Copy: [100 %]"):
                virsh.blockjob(vm_name, 'vda', options=' --pivot', debug=True,
                               ignore_status=False)
        # Check no output after abort.
        result = virsh.blockjob(vm_name, 'vda', options=' --raw', debug=True,
                                ignore_status=False)
        check_obj.check_blockjob_raw_result(result, no_output=True)
        # Clean copy file
        process.run('rm -rf %s' % tmp_copy_path)

    # Process cartesian parameters
    vm_name = params.get("main_vm")
    vm = env.get_vm(vm_name)
    case_name = params.get('case_name', 'blockjob')

    # Create object
    test_obj = blockcommand_base.BlockCommand(test, vm, params)
    check_obj = check_functions.Checkfunction(test, vm, params)

    vmxml = vm_xml.VMXML.new_from_inactive_dumpxml(vm_name)
    bkxml = vmxml.copy()
    tmp_copy_path = os.path.join(os.path.dirname(
        test_obj.get_first_disk_source()), "%s_blockcopy.img" % vm_name)
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
