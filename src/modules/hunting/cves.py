import logging
import json
import requests

from ...core.events import handler
from ...core.events.types import Vulnerability, Event, K8sVersionDisclosure
from ...core.types import Hunter, ActiveHunter, KubernetesCluster, RemoteCodeExec, AccessRisk, InformationDisclosure, \
    PrivilegeEscalation, DenialOfService, KubectlClient
from ..discovery.kubectl import KubectlClientEvent

from packaging import version

""" CVE Vulnerabilities """

class ServerApiVersionEndPointAccessPE(Vulnerability, Event):
    """Node is vulnerable to critical CVE-2018-1002105"""
    def __init__(self, evidence):
        Vulnerability.__init__(self, KubernetesCluster, name="Critical Privilege Escalation CVE", category=PrivilegeEscalation)
        self.evidence = evidence

class ServerApiVersionEndPointAccessDos(Vulnerability, Event):
    """Node not patched for CVE-2019-1002100. Depending on your RBAC settings, a crafted json-patch could cause a Denial of Service."""
    def __init__(self, evidence):
        Vulnerability.__init__(self, KubernetesCluster, name="Denial of Service to Kubernetes API Server", category=DenialOfService)
        self.evidence = evidence

class IncompleteFixToKubectlCpVulnerability(Vulnerability, Event):
    """The kubectl client is vulnerable to CVE-2019-11246, an attacker could potentially execute arbitrary code on the client's machine"""
    def __init__(self, binary_version):
        Vulnerability.__init__(self, KubectlClient, "Kubectl Vulnerable To CVE-2019-11246", category=RemoteCodeExec)
        self.binary_version = binary_version
        self.evidence = "kubectl version: {}".format(self.binary_version)

class KubectlCpVulnerability(Vulnerability, Event):
    """The kubectl client is vulnerable to CVE-2019-1002101, an attacker could potentially execute arbitrary code on the client's machine"""
    def __init__(self, binary_version):
        Vulnerability.__init__(self, KubectlClient, "Kubectl Vulnerable To CVE-2019-1002101", category=RemoteCodeExec)
        self.binary_version = binary_version
        self.evidence = "kubectl version: {}".format(self.binary_version)


class CveUtils:
    @staticmethod
    def get_base_release(full_ver):
        # if LecacyVersion, converting manually to a base version
        if type(full_ver) == version.LegacyVersion:
            return version.parse('.'.join(full_ver._version.split('.')[:2]))
        else:
            return version.parse('.'.join(map(str, full_ver._version.release[:2])))

    @staticmethod
    def to_legacy(full_ver):
        # converting version to verison.LegacyVersion
        return version.LegacyVersion('.'.join(map(str, full_ver._version.release)))

    @staticmethod
    def to_raw_version(v):
        if type(v) != version.LegacyVersion:
            return '.'.join(map(str, v._version.release))
        return v._version
        
    @staticmethod
    def version_compare(v1, v2):
        """Function compares two versions, handling differences with convertion to LegacyVersion"""
        # getting raw version, while striping 'v' char at the start. if exists. 
        # removing this char lets us safely compare the two version.
        v1_raw, v2_raw = CveUtils.to_raw_version(v1).strip('v'), CveUtils.to_raw_version(v2).strip('v')
        new_v1 = version.LegacyVersion(v1_raw)
        new_v2 = version.LegacyVersion(v2_raw)
        
        return CveUtils.basic_compare(new_v1, new_v2)

    @staticmethod
    def basic_compare(v1, v2):
        return (v1>v2)-(v1<v2)

    @staticmethod
    def is_vulnerable(fix_versions, check_version):
        """Function determines if a version is vulnerable, by comparing to given fix versions by base release"""
        vulnerable = False
        check_v = version.parse(check_version)
        base_check_v = CveUtils.get_base_release(check_v)
        
        # default to classic compare, unless the check_version is legacy.
        version_compare_func = CveUtils.basic_compare
        if type(check_v) == version.LegacyVersion:
            version_compare_func = CveUtils.version_compare

        if check_version not in fix_versions:
            # comparing ease base release for a fix
            for fix_v in fix_versions:
                fix_v = version.parse(fix_v)
                base_fix_v = CveUtils.get_base_release(fix_v)

                # if the check version and the current fix has the same base release 
                if base_check_v == base_fix_v:
                    # when check_version is legacy, we use a custom compare func, to handle differnces between versions.                    
                    if version_compare_func(check_v, fix_v) == -1:
                        # determine vulnerable if smaller and with same base version
                        vulnerable = True
                        break

        # if we did't find a fix in the fix releases, checking if the version is smaller that the first fix 
        if not vulnerable and version_compare_func(check_v, version.parse(fix_versions[0])) == -1:
            vulnerable = True

        return vulnerable


@handler.subscribe_once(K8sVersionDisclosure)
class K8sClusterCveHunter(Hunter):
    """K8s CVE Hunter
    Checks if Node is running a Kubernetes version vulnerable to known CVEs
    """

    def __init__(self, event):
        self.event = event

    def execute(self):
        logging.debug('Api Cve Hunter got version from the API server: {}'.format(self.event.version))
        fix_versions_cve_2018_1002105 = ["1.10.11", "1.11.5", "1.12.3"]
        fix_versions_cve_2019_1002100 = ["1.11.8", "1.12.6", "1.13.4"]
        
        if CveUtils.is_vulnerable(fix_versions_cve_2018_1002105, self.event.version):
            self.publish_event(ServerApiVersionEndPointAccessPE(self.event.version))

        if CveUtils.is_vulnerable(fix_versions_cve_2019_1002100, self.event.version):
            self.publish_event(ServerApiVersionEndPointAccessDos(self.event.version))


@handler.subscribe(KubectlClientEvent)
class KubectlCVEHunter(Hunter):
    """Kubectl CVE Hunter
    Checks if the kubectl client is vulnerable to known CVEs
    """
    def __init__(self, event):
        self.event = event

    def execute(self):
        cve_2019_1002101_fix_versions = ['1.11.9', '1.12.7', '1.13.5' '1.14.0']
        cve_2019_11246_fix_versions = ['1.12.9', '1.13.6', '1.14.2']

        if CveUtils.is_vulnerable(fix_versions=cve_2019_1002101_fix_versions, check_version=self.event.version):
            self.publish_event(KubectlCpVulnerability(binary_version=self.event.version))

        if CveUtils.is_vulnerable(fix_versions=cve_2019_11246_fix_versions, check_version=self.event.version):
            self.publish_event(IncompleteFixToKubectlCpVulnerability(binary_version=self.event.version))