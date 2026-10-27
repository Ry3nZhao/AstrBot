import {
  EXTENSION_DETAILS_ROUTE_NAME,
  EXTENSION_ROUTE_NAME
} from './routeConstants.mjs';
import type { RouteLocationNormalized } from 'vue-router';

const redirectToDataTab = (name: string) => (to: RouteLocationNormalized) => ({
  name,
  query: to.query,
  hash: to.hash
});

const MainRoutes = {
  path: '/main',
  meta: {
    requiresAuth: true
  },
  redirect: '/welcome',
  component: () => import('@/layouts/full/FullLayout.vue'),
  children: [
    {
      name: 'MainPage',
      path: '/',
      component: () => import('@/views/WelcomePage.vue')
    },
    {
      name: 'Welcome',
      path: '/welcome',
      component: () => import('@/views/WelcomePage.vue')
    },
    {
      path: '/extension',
      component: () => import('@/views/extension/PluginWorkspacePage.vue'),
      children: [
        {
          path: '',
          redirect: (to: RouteLocationNormalized) => {
            const legacyTab = String(to.hash || '').replace(/^#/, '');
            const routeNames: Record<string, string> = {
              market: 'ExtensionMarketplace',
              components: 'ExtensionComponents'
            };
            return {
              name: routeNames[legacyTab] || EXTENSION_ROUTE_NAME,
              query: to.query
            };
          }
        },
        {
          name: EXTENSION_ROUTE_NAME,
          path: 'plugins',
          component: () => import('@/views/ExtensionPage.vue'),
          props: { initialTab: 'installed' },
          meta: { extensionTab: 'installed', pluginView: 'installed' }
        },
        {
          name: 'ExtensionMarketplace',
          path: 'plugins/market',
          component: () => import('@/views/ExtensionPage.vue'),
          props: { initialTab: 'market' },
          meta: { extensionTab: 'installed', pluginView: 'market' }
        },
        {
          name: 'ExtensionComponents',
          path: 'components',
          component: () => import('@/views/extension/ComponentsPage.vue'),
          meta: { extensionTab: 'components' }
        },
        {
          name: EXTENSION_DETAILS_ROUTE_NAME,
          path: 'plugins/:pluginId',
          component: () => import('@/views/ExtensionPage.vue'),
          props: { initialTab: 'installed' },
          meta: { extensionTab: 'installed', pluginView: 'installed' }
        },
        {
          name: 'ExtensionMarketDetails',
          path: 'plugins/market/:pluginId',
          component: () => import('@/views/ExtensionPage.vue'),
          props: { initialTab: 'market' },
          meta: { extensionTab: 'installed', pluginView: 'market' }
        }
      ]
    },
    {
      name: 'PluginView',
      path: '/plugin-view/:pluginName/:pageName',
      component: () => import('@/views/PluginViewPage.vue')
    },
    {
      // Legacy alias of the plugin view route.
      path: '/plugin-page/:pluginName/:pageName',
      redirect: (to: RouteLocationNormalized) => ({
        name: 'PluginView',
        params: to.params,
        query: to.query,
      })
    },
    {
      path: '/extension/:pluginId',
      redirect: (to: RouteLocationNormalized) => ({
        name:
          String(to.hash || '').replace(/^#/, '') === 'market'
            ? 'ExtensionMarketDetails'
            : EXTENSION_DETAILS_ROUTE_NAME,
        params: { pluginId: to.params.pluginId },
        query: to.query,
        hash: to.hash === '#plugin-components' ? to.hash : ''
      })
    },
    {
      path: '/extension/market',
      redirect: { name: 'ExtensionMarketplace' }
    },
    {
      path: '/extension/market/:pluginId',
      redirect: (to: RouteLocationNormalized) => ({
        name: 'ExtensionMarketDetails',
        params: { pluginId: to.params.pluginId },
        query: to.query
      })
    },
    {
      path: '/extension-marketplace',
      redirect: { name: 'ExtensionMarketplace' }
    },
    {
      name: 'Platforms',
      path: '/platforms',
      component: () => import('@/views/PlatformPage.vue')
    },
    {
      name: 'Configs',
      path: '/config',
      component: () => import('@/views/ConfigPage.vue')
    },
    {
      path: '/normal',
      redirect: '/config'
    },
    {
      path: '/system',
      redirect: '/settings#system-config'
    },
    {
      name: 'SessionManagement',
      path: '/session-management',
      component: () => import('@/views/SessionManagementPage.vue')
    },
    {
      name: 'Data',
      path: '/data',
      component: () => import('@/views/DataPage.vue'),
      // Reopen the last visited tab, falling back to Statistics by default.
      redirect: (to: RouteLocationNormalized) => {
        const lastTab = localStorage.getItem('data_last_tab');
        return redirectToDataTab(
          lastTab && ['Stats', 'Console', 'Trace'].includes(lastTab) ? lastTab : 'Stats'
        )(to);
      },
      children: [
        {
          name: 'Stats',
          path: 'statistics',
          component: () => import('@/views/stats/StatsPage.vue'),
          meta: { dataTab: 'statistics' }
        },
        {
          name: 'Console',
          path: 'logs',
          component: () => import('@/views/ConsolePage.vue'),
          meta: { dataTab: 'logs' }
        },
        {
          name: 'Trace',
          path: 'trace',
          component: () => import('@/views/TracePage.vue'),
          meta: { dataTab: 'trace' }
        }
      ]
    },
    {
      path: '/dashboard/default',
      redirect: redirectToDataTab('Stats')
    },
    {
      path: '/console',
      redirect: redirectToDataTab('Console')
    },
    {
      path: '/trace',
      redirect: redirectToDataTab('Trace')
    },
    {
      path: '/observability',
      redirect: redirectToDataTab('Stats')
    },
    {
      name: 'Settings',
      path: '/settings',
      component: () => import('@/views/Settings.vue')
    },
    {
      name: 'About',
      path: '/about',
      component: () => import('@/views/AboutPage.vue')
    }
  ]
};

export default MainRoutes;
