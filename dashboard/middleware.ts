import { NextRequest, NextResponse } from 'next/server';

export function middleware(request: NextRequest) {
  const authCookie = request.cookies.get('dashboard_auth');
  const isAuthenticated = authCookie?.value === 'authenticated';
  const isLoginPage = request.nextUrl.pathname === '/login';
  const isSettingsPage = request.nextUrl.pathname === '/settings';

  // Redirect authenticated users away from login page to settings
  if (isLoginPage && isAuthenticated) {
    return NextResponse.redirect(new URL('/settings', request.url));
  }

  // Only protect the settings page - require authentication
  if (isSettingsPage && !isAuthenticated) {
    return NextResponse.redirect(new URL('/login', request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - public files (public directory)
     */
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
};
