import type { NodeKind, Status } from '../../domain/graph';
import { TargetIcon, LayersIcon, PlayIcon, CodeIcon, FlaskIcon, DiamondIcon, XIcon } from '../icons';
import './Legend.css';

/** The two orthogonal axes the whole UI reads by (spec §6): node KIND -> shape/icon,
 *  STATUS -> color. The Legend just names them so the map/board are decodable. */
const KINDS: { kind: NodeKind; label: string; Icon: typeof TargetIcon }[] = [
  { kind: 'objective', label: 'Objective', Icon: TargetIcon },
  { kind: 'ticket', label: 'Ticket', Icon: LayersIcon },
  { kind: 'step', label: 'Step', Icon: PlayIcon },
  { kind: 'code_region', label: 'CodeRegion', Icon: CodeIcon },
  { kind: 'test', label: 'Test', Icon: FlaskIcon },
  { kind: 'decision', label: 'Decision', Icon: DiamondIcon },
];

const STATUSES: { status: Status; label: string }[] = [
  { status: 'planning', label: 'planned' },
  { status: 'executing', label: 'executing' },
  { status: 'awaiting_review', label: 'awaiting review' },
  { status: 'done', label: 'done' },
  { status: 'blocked', label: 'blocked' },
];

export function Legend({ onClose }: { onClose: () => void }) {
  return (
    <>
      <div className="legend__scrim" onClick={onClose} aria-hidden="true" />
      <div className="legend" role="dialog" aria-label="범례">
        <header className="legend__head">
          <span className="legend__title">Legend</span>
          <button className="legend__close" aria-label="닫기" onClick={onClose}>
            <XIcon size={14} />
          </button>
        </header>

        <section className="legend__section">
          <span className="legend__label">NODE KIND — shape</span>
          <ul className="legend__list">
            {KINDS.map(({ kind, label, Icon }) => (
              <li key={kind} className="legend__row">
                <span className="legend__icon">
                  <Icon size={14} />
                </span>
                {label}
              </li>
            ))}
          </ul>
        </section>

        <section className="legend__section">
          <span className="legend__label">STATUS — color</span>
          <ul className="legend__list">
            {STATUSES.map(({ status, label }) => (
              <li key={status} className="legend__row">
                <span className={`pill pill--${status}`}>
                  <span className="dot" />
                  {label}
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}
