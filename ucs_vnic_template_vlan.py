#!/usr/bin/python

ANSIBLE_METADATA = {'metadata_version': '1.0',
                    'status': ['preview'],
                    'supported by': 'alexwr',
                    'version':'0.1'}

DOCUMENTATION = '''

---
module: ucs_vnic_template_vlan
short_description: Allows editing of vnic template vlans
description:
        - Manages additions or removals of vlans on vnic templates on UCS Manager.
version_added: "2.3"
author: Alex White-Robinson
extends_documentation_fragment: ucs

options:
    vlan_name:
        description: Name of the vlan to be added to the vnic template.
        required: true
    vnic_template_name:
        description: Name of the vnic template to modify.
        required: true
    org:
        description: 
            - List of the org heirarchy the vnic template lives in. 
              For example, for root/ccl provide ['root', 'ccl'].
              For root/ccl/polaris provide ['root', 'ccl', 'polaris'].
    policy owner:
        description: Entity that owns the policy.
        required: false
        default: local
        choices: ['local','policy','pending-policy']
    hostname:
        description: hostname or IP address of UCS Manager.
        required: true
    username:
        description: Username credential for UCS Manager.
        required: true
    password:
        description: Password credential for UCS Manager.
        required: true

requirements: ucsmsdk v0.9.3.1 or higher

notes: check_mode not yet supported
'''

EXAMPLES = '''

# Ensure vlan test-vlan_666 is on vnic template data-A in org root/company/test.
- name: Configure ucs vlans on local vnic templates
  ucs_vnic_template_vlan:
    hostname: {{inventory_hostname}}
    login: "{{username}}"
    password: {{password}}
    policy_owner: 'local'
    vlan_name: "test-vlan_666"
    vnic_template_name: "data-A"
    org: ['root', 'company', 'test']

# Ensure vlans in CHC are on vnic templates in org root/customer_1.
- name: Config ucs vlans
  ucs_vnic_template_vlan:
    hostname: {{inventory_hostname}}
    login: "{{username}}"
    password: {{password}}
    vlan_name: "{{item.0.vlan_name}}"
    vnic_template_name: "item.2"
    org: item.1
  with_nested:
    - {{vlans}}
    - ['root', 'customer_1']
    - {{vnic_templates}}
'''

RETURN = '''
logged_in: 
    description: Bool representing successful login to UCS Manager
    type: boolean
    sample: True
    returned: If login to UCS Manager occurred successfully

logged_out: 
    description: Bool representing successful logout from UCS Manager
    type: boolean
    sample: True
    returned: If logout of UCS managed occurred successfully

changed:
    description: check to see if a change was made on the device
    returned: always
    type: boolean
    sample: True
'''


from ucsmsdk.mometa.vnic.VnicEtherIf import VnicEtherIf
from ucsmsdk.ucshandle import UcsHandle

class UCS(object):
    def __init__(self, ucsm_ip="", ucsm_login="", ucsm_pw=""):
        self.handle = UcsHandle(ucsm_ip, ucsm_login ,ucsm_pw)
        self.ucsm_ip = ucsm_ip
        self.ucsm_pw = ucsm_pw
        self.ucsm_login = ucsm_login

    def login(self):
        self.handle.login()

    def logout(self):
        self.handle.logout()


def check_if_vlan_on_vnic(ucsm, vnic_templ_dn, vlan_name):
	#query for all child objects on the vnic template
        proposed_vlan_dn = vnic_templ_dn + "/if-" + vlan_name
        vnic_vlan_query = ucsm.handle.query_dn(proposed_vlan_dn)
        #for each child object on vnic template...
        if vnic_vlan_query:
        #If this value is true, the vlan is on vnic template
            return True
        else:
        #If this value is false, the vlan is not on vnic template
	    return False

def log_into_ucs(ucsm, module, results):
    try:
       	ucsm.login()
       	results['logged_in'] = True
    except Exception as e:
       	module.fail_json(msg=e)
    return results

def log_out_of_ucs(ucsm, module, results):
    #log out of ucs manager
    try:
        ucsm.handle.logout()
        results['logged_out'] = True
    except Exception as e:
        module.fail_json(msg=e)
    return results
        


def check_vlan_exists_on_fi(ucsm, vlan_name):
    #This string is used to check if the VLAN exists on the FIs
    #if you add the vlan to the vnic template without it existing on the FIs
    #you a) can't remove it from the vnic properly and
    #    b) when you add it to the FIs it bounces all associated NICs, not desired in normal operation
    filter_string = '(name, {0}, type="eq")'.format(vlan_name)
    #So this check to make sure the vlan is actually on the FIs is very important
    vlan_exists = ucsm.handle.query_classid(class_id="fabricVlan",
                                                filter_str=filter_string)
    #if using pinned vlans / vlan groups to multiple uplink port-channels
    #then when you add a vlan to the vnic template you must make sure you're not
    #adding vlans from a vlan group other than the one on that template
    #ucsm will drop all interfaces because the vlans can't resolve to a single uplink
    if vlan_exists:
	return True
    else:
	return False

def add_vlan_to_vnic_template(ucsm, module, vnic_templ_dn, vlan_name, vlan_on_vnic_template, results):
    #uses the VnicEtherIf class imported earlier to specify
    #the vlan you want to add to the vnic template
    #vlan specified in 'name', target vnic template is the 
    #'parent_mo_or_dn' value
    mo = VnicEtherIf(parent_mo_or_dn=vnic_templ_dn, default_net="no", name=str(vlan_name))
    try:
        #Add the vlan to the vnic template
        if not vlan_on_vnic_template:
            ucsm.handle.add_mo(mo)
	    #have not figured out how to deal with what ucsm calls 'ambigious impact' in GUI
	    #ucsm doesn't apply this change if results are unknown, example if a server is in 'config error' state
	    #doesn't error out here but doesn't actually apply
            ucsm.handle.commit()
            results['changed'] = True
    except Exception as e:
        module.fail_json(msg=e)
        results['changed'] = False

    #return results dictionary with the changed / unchanged value
    return results


def main():
    module = AnsibleModule(
        argument_spec       = dict(
        vlan_name           = dict(required=True),
        vnic_template_name  = dict(required=True),
        org                 = dict(required=True, type='list'),
        policy_owner        = dict(default = 'local', 
                                    choices = ['local', 'pending-policy', 'policy']),
        hostname            = dict(required=True),
        password            = dict(required=True, no_log=True),
        username            = dict(required=True),
        )
    )
    
    vlan_name = module.params.get('vlan_name')
    org = module.params.get('org', [])
    vnic_template_name = module.params.get('vnic_template_name')    
    ucsm_ip = module.params.get('hostname')
    ucsm_login = module.params.get('username')
    ucsm_pw = module.params.get('password')
    policy_owner = module.params.get('policy_owner')
    
    ucsm = UCS(ucsm_ip, ucsm_login, ucsm_pw)
    results = {}
    vnic_templ_dn = ''

    for org_name in org:
        vnic_templ_dn += str('org-' + org_name + '/')
    vnic_templ_dn += str("lan-conn-templ-" + vnic_template_name)

    results = log_into_ucs(ucsm, module, results)
    vlan_on_vnic_template = check_if_vlan_on_vnic(ucsm, vnic_templ_dn, vlan_name)
    vlan_on_fi = check_vlan_exists_on_fi(ucsm, vlan_name)
    #If the vlan isn't on the FIs, fail the module
    #might rethink this and just 'break' and give a unchanged result
    #Really important to not apply the VLAN to vnic templates if it's not on the FIs
    #Consequence of not being able to remove the vlan OR define it without an outage on vnics
    #that are associated to the template at the time
    if not vlan_on_fi:
        results['changed'] = False
        module.fail_json(msg='VLAN does not exist on UCS Fabric Interconnects')

    elif not vlan_on_vnic_template:
        results = add_vlan_to_vnic_template(ucsm, module, vnic_templ_dn, vlan_name, vlan_on_vnic_template, results)
	results = log_out_of_ucs(ucsm, module, results)
        module.exit_json(**results)

    else:
	results['changed'] = False
	results = log_out_of_ucs(ucsm, module, results)
        module.exit_json(**results)

from ansible.module_utils.basic import *
if __name__ == '__main__':
    main()
