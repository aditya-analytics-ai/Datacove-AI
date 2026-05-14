/**
 * Skeleton.jsx — Reusable skeleton loading components
 */
import React from "react";

const shimmer = `
  @keyframes shimmer {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
  }
`;

export function Skeleton({ width, height, radius = 6, style }) {
  return (
    <>
      <style>{shimmer}</style>
      <div style={{
        width: width || '100%',
        height: height || 20,
        borderRadius: radius,
        background: 'linear-gradient(90deg, var(--surface-2) 25%, var(--surface-3) 50%, var(--surface-2) 75%)',
        backgroundSize: '200% 100%',
        animation: 'shimmer 1.5s ease-in-out infinite',
        ...style,
      }} />
    </>
  );
}

export function SkeletonText({ lines = 3, gap = 8 }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap }}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} width={i === lines - 1 ? '70%' : '100%'} height={14} />
      ))}
    </div>
  );
}

export function SkeletonCard({ style }) {
  return (
    <div style={{
      background: 'var(--surface-1)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
      padding: 20,
      ...style,
    }}>
      <Skeleton width={60} height={12} style={{ marginBottom: 12 }} />
      <Skeleton width="80%" height={24} style={{ marginBottom: 8 }} />
      <Skeleton width="50%" height={14} />
    </div>
  );
}

export function SkeletonTable({ rows = 5, cols = 4 }) {
  return (
    <div style={{ 
      background: 'var(--surface-1)', 
      border: '1px solid var(--border)', 
      borderRadius: 'var(--radius-lg)',
      overflow: 'hidden'
    }}>
      {/* Header */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: `repeat(${cols}, 1fr)`,
        gap: 12,
        padding: '12px 16px',
        background: 'var(--surface-2)',
        borderBottom: '1px solid var(--border)'
      }}>
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} width={80} height={12} />
        ))}
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <div key={rowIdx} style={{ 
          display: 'grid', 
          gridTemplateColumns: `repeat(${cols}, 1fr)`,
          gap: 12,
          padding: '12px 16px',
          borderBottom: rowIdx < rows - 1 ? '1px solid var(--border)' : 'none'
        }}>
          {Array.from({ length: cols }).map((_, i) => (
            <Skeleton key={i} width={i === 0 ? 120 : '80%'} height={14} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonStats({ count = 4 }) {
  return (
    <div style={{ 
      display: 'grid', 
      gridTemplateColumns: `repeat(${count}, 1fr)`,
      gap: 16
    }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} style={{
          background: 'var(--surface-1)',
          border: '1px solid var(--border)',
          borderRadius: 'var(--radius-lg)',
          padding: 20,
          display: 'flex',
          alignItems: 'center',
          gap: 14
        }}>
          <Skeleton width={40} height={40} radius={8} />
          <div style={{ flex: 1 }}>
            <Skeleton width={60} height={24} style={{ marginBottom: 6 }} />
            <Skeleton width={80} height={12} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function PageLoader({ title, subtitle }) {
  return (
    <div style={{ padding: 24 }}>
      {title && (
        <div style={{ marginBottom: 24 }}>
          <Skeleton width={200} height={28} style={{ marginBottom: 8 }} />
          {subtitle && <Skeleton width={300} height={16} />}
        </div>
      )}
      <SkeletonStats count={4} />
    </div>
  );
}

export default Skeleton;
