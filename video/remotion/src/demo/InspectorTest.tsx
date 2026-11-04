import {AbsoluteFill} from 'remotion';
import {ConfirmationsIntro, DevicesSidebar, INSPECTOR, InspectorHeader, InspectorNav, PendingCard} from './Inspector';
import {COLOR, MONO} from './theme';

export const InspectorTest: React.FC = () => (
  <AbsoluteFill style={{background: COLOR.bg}}>
    <InspectorHeader hub={{product: 'OpenHAL 0.1.0', host: '127.0.0.1:55659', protocol: '0.1', conformance: 'full'}} stopped={false} />
    <InspectorNav active="Confirmations" pending={1} />
    <DevicesSidebar top={INSPECTOR.headerHeight + INSPECTOR.navHeight} device={{name: 'SO-101 arm (simulated)', id: 'arm', driver: 'mujoco', conformance: 'full', hazard: 'medium'}} />
    <ConfirmationsIntro pending={1} />
    <PendingCard
      request={{
        agent: 'claude',
        principal: 'agent:claude',
        action: 'drop_in_bin',
        deviceName: 'SO-101 arm (simulated)',
        requestId: '7f424af1907606dd',
        requested: '1 s ago',
        method: 'hal/action',
        params: '{ "device": "arm", "action": "drop_in_bin", "args": {} }',
        does: 'Carry the part in the gripper over the bin and open the gripper. A dropped part can’t be put back.',
        why: (
          <>
            <span style={{fontFamily: MONO}}>arm.hal.yaml</span> requires a person to confirm <span style={{fontFamily: MONO}}>drop_in_bin</span> each time. Nothing reaches the device until you approve.
          </>
        ),
        expires: 299,
      }}
    />
  </AbsoluteFill>
);
