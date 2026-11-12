import { CSSProperties, ReactNode } from 'react';

interface CardProps {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  style?: CSSProperties;
}

/** The page section used everywhere: title bar (optional actions) + content. */
export function Card({ title, actions, children, style }: CardProps) {
  return (
    <div className="card" style={style}>
      {title ? (
        <div className="card-title">
          <span>{title}</span>
          {actions}
        </div>
      ) : null}
      {children}
    </div>
  );
}
