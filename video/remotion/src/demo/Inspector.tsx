import {COLOR, MONO, SANS} from './theme';

export const INSPECTOR = {headerHeight: 77, navHeight: 40, bannerHeight: 48, sidebar: 300, stop: {x: 1109, y: 14, w: 145, h: 48}};

const label: React.CSSProperties = {
  fontFamily: SANS,
  fontSize: 14,
  fontWeight: 700,
  color: COLOR.text2,
  fontVariantCaps: 'all-small-caps',
  letterSpacing: '0.04em',
};

const Fact: React.FC<{name: string; children: React.ReactNode}> = ({name, children}) => (
  <div style={{display: 'grid', gap: 2}}>
    <div style={label}>{name}</div>
    <div style={{fontSize: 15, lineHeight: 1.3}}>{children}</div>
  </div>
);

export type HubFacts = {product: string; host: string; protocol: string; conformance: string};

export const InspectorHeader: React.FC<{hub: HubFacts; stopped: boolean; pressed?: number}> = ({hub, stopped, pressed = 0}) => (
  <div
    style={{
      position: 'absolute',
      left: 0,
      top: 0,
      width: 1280,
      height: INSPECTOR.headerHeight,
      borderBottom: `1px solid ${COLOR.border}`,
      background: COLOR.bg,
      fontFamily: SANS,
      color: COLOR.text,
    }}
  >
    <div style={{position: 'absolute', left: 25, top: 22, display: 'flex', alignItems: 'baseline', gap: 9}}>
      <span style={{fontWeight: 700, fontSize: 21, letterSpacing: '-0.04em'}}>OpenHAL</span>
      <span style={{fontSize: 20, color: COLOR.text2, letterSpacing: '-0.02em'}}>Inspector</span>
    </div>
    {[
      {x: 237, name: 'Hub', body: (
        <>
          {hub.product} <span style={{color: COLOR.text2}}>at</span> <span style={{fontFamily: MONO}}>{hub.host}</span>
        </>
      )},
      {x: 514, name: 'Connection', body: <span style={{color: COLOR.ok, fontWeight: 700}}>live</span>},
      {x: 650, name: 'Protocol', body: <span style={{fontFamily: MONO}}>{hub.protocol}</span>},
      {x: 730, name: 'Conformance', body: hub.conformance},
    ].map((fact) => (
      <div key={fact.name} style={{position: 'absolute', left: fact.x, top: 17}}>
        <Fact name={fact.name}>{fact.body}</Fact>
      </div>
    ))}
    {stopped ? (
      <div
        style={{
          position: 'absolute',
          right: 25,
          top: 20,
          width: 98,
          height: 36,
          borderRadius: 6,
          boxShadow: `inset 0 0 0 1.5px ${COLOR.text2}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: COLOR.blocked,
          fontWeight: 700,
          fontSize: 16,
          letterSpacing: '0.08em',
        }}
      >
        UNLOCK
      </div>
    ) : (
      <div
        style={{
          position: 'absolute',
          left: INSPECTOR.stop.x,
          top: INSPECTOR.stop.y,
          width: INSPECTOR.stop.w,
          height: INSPECTOR.stop.h,
          borderRadius: 6,
          background: COLOR.blocked,
          border: `2px solid ${COLOR.blocked}`,
          boxShadow: `inset 0 0 0 ${2 + pressed}px ${COLOR.bg}`,
          boxSizing: 'border-box',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: COLOR.bg,
          fontWeight: 700,
          fontSize: 24,
          letterSpacing: '0.08em',
          scale: `${1 - 0.03 * pressed}`,
        }}
      >
        STOP
      </div>
    )}
  </div>
);

const TABS = ['Devices', 'Confirmations', 'Audit log', 'Routines', 'Driver writer', 'Settings'];

export const InspectorNav: React.FC<{active: string; pending?: number}> = ({active, pending = 0}) => (
  <div
    style={{
      position: 'absolute',
      left: 0,
      top: INSPECTOR.headerHeight,
      width: 1280,
      height: INSPECTOR.navHeight,
      borderBottom: `1px solid ${COLOR.border}`,
      display: 'flex',
      alignItems: 'stretch',
      padding: '0 16px',
      fontFamily: SANS,
      fontWeight: 700,
      fontSize: 15,
    }}
  >
    {TABS.map((tab) => (
      <div
        key={tab}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '0 8px',
          marginBottom: -1,
          color: tab === active ? COLOR.text : COLOR.text2,
          borderBottom: `2px solid ${tab === active ? COLOR.accent : 'transparent'}`,
        }}
      >
        {tab}
        {tab === 'Confirmations' && pending > 0 ? <span style={{fontFamily: MONO, color: COLOR.confirm}}>{pending}</span> : null}
      </div>
    ))}
    <div style={{marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8, color: COLOR.text2, paddingRight: 8}}>
      <span style={{fontWeight: 400}}>↓</span> Message log
    </div>
  </div>
);

export const StoppedBanner: React.FC<{reason: string; opacity?: number; top?: number}> = ({reason, opacity = 1, top = INSPECTOR.headerHeight + INSPECTOR.navHeight}) => (
  <div
    style={{
      position: 'absolute',
      left: 0,
      top,
      width: 1280,
      height: INSPECTOR.bannerHeight,
      background: COLOR.surface,
      borderBottom: `1px solid ${COLOR.border}`,
      display: 'flex',
      alignItems: 'center',
      gap: 16,
      padding: '0 24px',
      fontFamily: SANS,
      fontSize: 15,
      color: COLOR.text,
      opacity,
    }}
  >
    <span style={{color: COLOR.blocked, fontWeight: 700}}>stopped</span>
    <span>
      Every command is blocked with{' '}
      <span style={{color: COLOR.blocked, fontWeight: 700, fontFamily: MONO}}>error -32014 STOPPED</span> until a person lifts the stop with UNLOCK.
    </span>
    <span>
      <span style={label}>Reason</span> {reason}
    </span>
  </div>
);

export type DeviceSummary = {name: string; id: string; driver: string; conformance: string; hazard: string};

export const DevicesSidebar: React.FC<{device: DeviceSummary; top: number; selected?: boolean}> = ({device, top, selected}) => (
  <div style={{position: 'absolute', left: 0, top, width: INSPECTOR.sidebar, bottom: 0, borderRight: `1px solid ${COLOR.border}`, fontFamily: SANS, color: COLOR.text}}>
    <div style={{position: 'absolute', left: 16, right: 18, top: 18, display: 'flex', justifyContent: 'space-between', alignItems: 'baseline'}}>
      <span style={{fontWeight: 700, fontSize: 18}}>Devices</span>
      <span style={{fontSize: 14, color: COLOR.text2}}>1 registered, 1 connected</span>
    </div>
    <div style={{position: 'absolute', left: 16, right: 18, top: 52, padding: '10px 12px', borderRadius: 6, background: COLOR.surface, fontSize: 14, color: COLOR.text2}}>
      <span style={label}>Demo data</span> 1 of 1 device is simulated.
    </div>
    <div
      style={{
        position: 'absolute',
        left: 16,
        right: 18,
        top: 104,
        padding: '14px 12px',
        borderRadius: 6,
        boxShadow: `inset 0 0 0 1px ${selected ? COLOR.accent : COLOR.border}`,
        background: selected ? COLOR.surface : 'transparent',
        display: 'grid',
        gap: 6,
        fontSize: 15,
      }}
    >
      <div style={{fontWeight: 700, fontSize: 16}}>{device.name}</div>
      <div style={{display: 'flex', gap: 8, alignItems: 'center'}}>
        <span style={{fontFamily: MONO}}>{device.id}</span>
        <span style={{padding: '1px 6px', borderRadius: 4, background: COLOR.bg, color: COLOR.text2}}>simulated</span>
      </div>
      <div style={{display: 'flex', gap: 12, fontWeight: 700}}>
        <span style={{color: COLOR.ok}}>connected</span>
        <span style={{color: COLOR.text2}}>unverified</span>
      </div>
      <div style={{display: 'flex', gap: 12, alignItems: 'baseline'}}>
        <span>
          <span style={label}>Driver</span> <span style={{fontFamily: MONO}}>{device.driver}</span>
        </span>
        <span>
          <span style={label}>Conformance</span> {device.conformance}
        </span>
      </div>
      <div>
        <span style={label}>Hazard</span> {device.hazard}
      </div>
    </div>
  </div>
);

export type PendingRequest = {
  agent: string;
  principal: string;
  action: string;
  deviceName: string;
  requestId: string;
  requested: string;
  method: string;
  params: string;
  does: string;
  why: React.ReactNode;
  expires: number;
};

const Mono: React.FC<{children: React.ReactNode; muted?: boolean}> = ({children, muted}) => (
  <span style={{fontFamily: MONO, fontSize: '0.92em', color: muted ? COLOR.text2 : undefined}}>{children}</span>
);

export const Json: React.FC<{text: string}> = ({text}) => (
  <>
    {text.split(/("[^"]*"\s*:)/).map((part, i) => (
      <span key={i} style={{color: part.endsWith(':') ? COLOR.text2 : COLOR.text}}>
        {part}
      </span>
    ))}
  </>
);

export const PendingCard: React.FC<{request: PendingRequest; approvePress?: number; hover?: boolean; approved?: boolean}> = ({request, approvePress = 0, hover, approved}) => (
  <div style={{position: 'absolute', left: 333, top: 294, width: 915, height: 314, borderRadius: 6, boxShadow: `inset 0 0 0 1px ${COLOR.border}`, overflow: 'hidden', fontFamily: SANS, color: COLOR.text}}>
    <div style={{position: 'absolute', left: 8, top: 8, bottom: 8, width: 560, borderLeft: `2px dashed ${COLOR.text2}`, padding: '10px 16px', display: 'grid', alignContent: 'start', gap: 10}}>
      <div style={{fontWeight: 700, fontSize: 18, lineHeight: 1.4}}>
        The agent <Mono>{request.agent}</Mono> sends a request to run <Mono>{request.action}</Mono> on {request.deviceName}.
      </div>
      <div style={{display: 'flex', gap: 12, fontSize: 16, color: COLOR.text2}}>
        <Mono muted>{request.principal}</Mono>
        <span>requested {request.requested}</span>
        <Mono muted>request {request.requestId}</Mono>
      </div>
      <div style={{display: 'flex', gap: 12, alignItems: 'baseline', fontFamily: MONO, fontSize: 15}}>
        <span>⟶</span>
        <span style={{fontWeight: 700}}>{request.method}</span>
      </div>
      <div style={{fontFamily: MONO, fontSize: 15.5}}>
        <Json text={request.params} />
      </div>
      <div style={{display: 'grid', gridTemplateColumns: '150px 1fr', gap: '10px 14px', fontSize: 16, lineHeight: 1.45}}>
        <span style={label}>what {request.action} does</span>
        <span>{request.does}</span>
        <span style={label}>why the request is held</span>
        <span>{request.why}</span>
      </div>
    </div>
    <div style={{position: 'absolute', left: 575, top: 0, right: 0, bottom: 0, background: COLOR.surface, borderLeft: `2px solid ${COLOR.text}`, padding: 16, display: 'grid', alignContent: 'start', gap: 12, fontSize: 15}}>
      <div style={label}>your decision</div>
      <div>
        Expires in <Mono>{request.expires} s</Mono>
      </div>
      <div
        style={{
          justifySelf: 'start',
          padding: '9px 16px',
          borderRadius: 6,
          background: hover ? '#de51a8' : COLOR.accentFill,
          boxShadow: `inset 0 0 0 1.5px ${COLOR.accent}`,
          translate: hover && !approvePress ? '0 -1px' : '0 0',
          color: COLOR.onAccent,
          fontWeight: 600,
          fontSize: 16,
          scale: `${1 - 0.04 * approvePress}`,
          opacity: approved ? 0.55 : 1,
        }}
      >
        Approve and run {request.action}
      </div>
      <div style={{color: COLOR.text2, fontSize: 14, lineHeight: 1.45}}>The Safety Kernel checks every limit again before the command runs.</div>
      <div style={{fontWeight: 700, color: COLOR.text2, fontSize: 14}}>Reason to reject, optional</div>
      <div style={{display: 'flex', gap: 8}}>
        <div style={{flex: 1, height: 34, borderRadius: 6, boxShadow: `inset 0 0 0 1.5px ${COLOR.border}`}} />
        <div style={{padding: '0 14px', height: 34, display: 'flex', alignItems: 'center', borderRadius: 6, boxShadow: `inset 0 0 0 1.5px ${COLOR.text2}`, fontWeight: 600}}>Reject</div>
      </div>
    </div>
  </div>
);

export const ConfirmationsIntro: React.FC<{pending: number}> = ({pending}) => (
  <div style={{position: 'absolute', left: 333, top: 140, width: 915, fontFamily: SANS, color: COLOR.text}}>
    <div style={{fontWeight: 700, fontSize: 22}}>Confirmations</div>
    <div style={{fontSize: 15, lineHeight: 1.45, color: COLOR.text2, marginTop: 10, maxWidth: 640}}>
      Commands an agent or routine sent that need a person. Approving runs every Safety Kernel check again against the current state before anything reaches the device.
    </div>
    <div style={{height: 1, background: COLOR.border, marginTop: 18}} />
    <div style={{fontWeight: 700, fontSize: 18, marginTop: 17}}>
      Pending <span style={{fontFamily: MONO, fontSize: 15, color: COLOR.text2}}>{pending}</span>
    </div>
    <div style={{height: 1, background: COLOR.border, marginTop: 360}} />
    <div style={{fontWeight: 700, fontSize: 18, marginTop: 24}}>Decided recently</div>
  </div>
);
