import type { ReactNode } from 'react';

export type BannerTone = 'sage' | 'sky' | 'butter' | 'peach' | 'lilac' | 'mint';

/**
 * The title of a page in a soft rounded banner: a short human title, one
 * friendly line under it, a small illustration and the page's main action.
 */
export function PageHeader({
  title,
  note,
  art,
  tone = 'sage',
  actions,
  children,
}: {
  title: string;
  note?: ReactNode;
  art?: ReactNode;
  tone?: BannerTone;
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className={`page-banner page-banner--${tone}`}>
      <div className="page-banner__text">
        <h1 className="page-title">{title}</h1>
        {note && <p className="page-banner__note">{note}</p>}
        {children}
      </div>
      {actions && <div className="page-banner__actions">{actions}</div>}
      {art && (
        <span className="page-banner__art" aria-hidden="true">
          {art}
        </span>
      )}
    </header>
  );
}
