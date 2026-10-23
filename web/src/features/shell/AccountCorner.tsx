import { api } from '../../api/client';
import { hrefFor } from '../../app/router';
import { useLoad } from '../../app/store';
import type { Account } from '../account/AccountPage';

/** Top-right of every page: sign in and sign up, or who is signed in. */
export function AccountCorner() {
  const account = useLoad(() => api<Account>('/account'), []).data;
  if (!account) return <div className="account-corner" />;
  return (
    <div className="account-corner">
      {account.signed_in ? (
        <a className="account-chip" href={hrefFor({ name: 'account' })} title={account.email ?? ''}>
          <span className="account-chip__avatar" aria-hidden="true">
            {(account.name ?? '?').slice(0, 1).toUpperCase()}
          </span>
          <span>
            <strong>{account.name}</strong>
            <small>Tài khoản của bạn</small>
          </span>
        </a>
      ) : (
        <>
          <a className="btn btn--ghost btn--sm" href={hrefFor({ name: 'account' })}>
            Đăng nhập
          </a>
          <a className="btn btn--primary btn--sm" href={hrefFor({ name: 'account', mode: 'register' })}>
            Đăng ký
          </a>
        </>
      )}
    </div>
  );
}
