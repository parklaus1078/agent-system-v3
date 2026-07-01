import { useState } from 'react';
import { useStore } from '../../store/useStore';
import { CheckIcon, XIcon } from '../icons';
import '../plan/PlanApproval.css';

/** View + edit the current project's title and description (the description originally
 *  entered at init). Saves via api.setProjectMeta -> Objective.label / data.description. */
export function ProjectMetaEditor({
  initialTitle,
  initialDescription,
  onClose,
}: {
  initialTitle: string;
  initialDescription: string;
  onClose: () => void;
}) {
  const api = useStore((s) => s.api);
  const [title, setTitle] = useState(initialTitle);
  const [description, setDescription] = useState(initialDescription);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.setProjectMeta({ title: title.trim(), description });
      onClose();
    } catch {
      setError('저장에 실패했습니다. 다시 시도해 주세요.');
      setBusy(false);
    }
  };

  return (
    <div className="plan">
      <header className="plan__head">
        <div className="plan__title">
          <span className="plan__goal">프로젝트 정보</span>
        </div>
        <button className="plan__close" aria-label="닫기" onClick={onClose} disabled={busy}>
          <XIcon size={16} />
        </button>
      </header>

      <label className="plan__desclabel">
        <span className="plan__desccap">제목</span>
        <input
          className="plan-step__input"
          aria-label="프로젝트 제목"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
      </label>
      <label className="plan__desclabel">
        <span className="plan__desccap">설명</span>
        <textarea
          className="plan__descinput"
          aria-label="프로젝트 설명"
          placeholder="이 프로젝트가 무엇을 만드는지."
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={4}
        />
      </label>

      <footer className="plan__foot">
        <span className="plan__note">
          {error ? (
            <span className="plan__error" role="alert">
              {error}
            </span>
          ) : (
            '제목·설명은 언제든 수정 가능합니다.'
          )}
        </span>
        <div className="plan__actions">
          <button className="btn btn--ghost" onClick={onClose} disabled={busy}>
            취소
          </button>
          <button className="btn btn--primary" onClick={save} disabled={busy || !title.trim()}>
            <CheckIcon size={15} />
            저장
          </button>
        </div>
      </footer>
    </div>
  );
}
