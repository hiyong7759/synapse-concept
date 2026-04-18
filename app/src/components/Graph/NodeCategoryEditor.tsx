import { useEffect, useState } from 'react';
import { api } from '../../api';
import styles from './NodeCategoryEditor.module.css';

interface Props {
  nodeId: number;
  onChanged?: () => void;  // 카테고리 변동 시 부모 알림 (그래프 리로드 등)
}

/**
 * v12 Phase 4: 노드 상세 패널의 카테고리 편집 영역.
 * - 칩으로 현재 카테고리 표시
 * - 칩 클릭 → 이름 변경(rename) 또는 삭제 모드
 * - 입력창 → 새 카테고리 추가 (기존 사용자 정의 경로 자동완성)
 */
export function NodeCategoryEditor({ nodeId, onChanged }: Props) {
  const [categories, setCategories] = useState<string[]>([]);
  const [allCategories, setAllCategories] = useState<string[]>([]);
  const [adding, setAdding] = useState(false);
  const [newCat, setNewCat] = useState('');
  const [editing, setEditing] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [loading, setLoading] = useState(false);

  async function reload() {
    setLoading(true);
    try {
      const [detail, all] = await Promise.all([
        api.nodeCategories(nodeId),
        api.categoriesAll(),
      ]);
      setCategories(detail.categories.map((c) => c.category));
      setAllCategories(all.map((c) => c.category));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, [nodeId]);

  async function handleAdd() {
    const cat = newCat.trim();
    if (!cat) return;
    await api.categoryAdd(nodeId, cat);
    setNewCat('');
    setAdding(false);
    await reload();
    onChanged?.();
  }

  async function handleRemove(cat: string) {
    if (!confirm(`'${cat}' 분류를 제거할까요?`)) return;
    await api.categoryRemove(nodeId, cat);
    await reload();
    onChanged?.();
  }

  async function handleRenameStart(cat: string) {
    setEditing(cat);
    setEditValue(cat);
  }

  async function handleRenameConfirm() {
    if (!editing) return;
    const to = editValue.trim();
    if (!to || to === editing) {
      setEditing(null);
      return;
    }
    await api.categoryRename(nodeId, editing, to);
    setEditing(null);
    await reload();
    onChanged?.();
  }

  // 자동완성 후보: 기존 카테고리에서 입력 prefix 매칭, 이미 부여된 건 제외
  const suggestions = allCategories.filter(
    (c) => !categories.includes(c) && (newCat ? c.toLowerCase().includes(newCat.toLowerCase()) : true),
  ).slice(0, 8);

  return (
    <div className={styles.editor}>
      <div className={styles.label}>분류</div>
      <div className={styles.chips}>
        {categories.length === 0 && !loading && (
          <span className={styles.empty}>아직 분류 없음</span>
        )}
        {categories.map((cat) =>
          editing === cat ? (
            <span key={cat} className={styles.chipEditing}>
              <input
                className={styles.chipInput}
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleRenameConfirm();
                  if (e.key === 'Escape') setEditing(null);
                }}
                autoFocus
              />
              <button className={styles.chipBtn} onClick={handleRenameConfirm}>✓</button>
              <button className={styles.chipBtn} onClick={() => setEditing(null)}>✕</button>
            </span>
          ) : (
            <span key={cat} className={styles.chip}>
              <span className={styles.chipText} onClick={() => handleRenameStart(cat)}>{cat}</span>
              <button className={styles.chipRemove} onClick={() => handleRemove(cat)}>×</button>
            </span>
          ),
        )}
        {!adding && (
          <button className={styles.addBtn} onClick={() => setAdding(true)}>+ 추가</button>
        )}
      </div>
      {adding && (
        <div className={styles.addRow}>
          <input
            className={styles.addInput}
            value={newCat}
            onChange={(e) => setNewCat(e.target.value)}
            placeholder="예: 병원.2026-04-18"
            list={`cats-${nodeId}`}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleAdd();
              if (e.key === 'Escape') { setAdding(false); setNewCat(''); }
            }}
            autoFocus
          />
          <datalist id={`cats-${nodeId}`}>
            {suggestions.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
          <button className={styles.addOk} onClick={handleAdd}>저장</button>
          <button className={styles.addCancel} onClick={() => { setAdding(false); setNewCat(''); }}>취소</button>
        </div>
      )}
    </div>
  );
}
