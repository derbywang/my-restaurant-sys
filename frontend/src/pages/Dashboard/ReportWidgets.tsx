import React from 'react';
import { formatCurrency } from '@ury/core';
import { Card, CardHeader, CardTitle, CardContent, Badge, Spinner } from '@ury/ui';
import { useBranchContext } from '../../context/BranchContext';
import { TransactionRecord } from '../../services/dashboard';
import { t } from '../../i18n';
import { orderTypeLabel, orderStatusLabel } from '../../i18n/labels';

interface ReportWidgetsProps {
  recentTransactions: TransactionRecord[];
  loading: boolean;
}

export const ReportWidgets: React.FC<ReportWidgetsProps> = ({ recentTransactions, loading }) => {
  const { activeBranchId, activeBranch } = useBranchContext();

  const activeBranchName = activeBranchId === 'all' ? t('layout.header.all_branches') : (activeBranch?.name || t('dashboard.widgets.selected_branch'));

  return (
    <div className="space-y-6">
      {/* Live POS Transactions */}
      <Card className="rounded-lg border border-gray-200 bg-white shadow-xs overflow-hidden">
        <CardHeader className="border-b border-gray-100 bg-gray-50/50 p-5">
          <div>
            <CardTitle className="text-lg font-bold text-gray-900">
              {t('dashboard.widgets.live_transactions')}
            </CardTitle>
            <p className="text-xs text-gray-500 mt-0.5">
              {t('dashboard.widgets.live_subtitle')}
            </p>
          </div>
        </CardHeader>

        <CardContent className="p-0">
          {loading ? (
            <div className="py-12 flex items-center justify-center">
              <Spinner className="w-6 h-6 text-primary" />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-gray-50 text-gray-500 font-semibold border-b border-gray-100">
                  <tr>
                    <th className="px-5 py-3.5">{t('dashboard.widgets.invoice_id')}</th>
                    <th className="px-5 py-3.5">{t('dashboard.widgets.customer')}</th>
                    <th className="px-5 py-3.5">{t('dashboard.widgets.table_location')}</th>
                    <th className="px-5 py-3.5">{t('dashboard.widgets.order_type')}</th>
                    <th className="px-5 py-3.5">{t('dashboard.widgets.date_time')}</th>
                    <th className="px-5 py-3.5">{t('dashboard.widgets.status')}</th>
                    <th className="px-5 py-3.5 text-right">{t('dashboard.widgets.grand_total')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 font-medium text-gray-700">
                  {recentTransactions.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-5 py-8 text-center text-gray-400">
                        {t('dashboard.widgets.no_transactions')}
                      </td>
                    </tr>
                  ) : (
                    recentTransactions.map((tx) => (
                      <tr key={tx.name} className="hover:bg-primary/10 transition-colors">
                        <td className="px-5 py-3.5 font-bold text-primary">{tx.name}</td>
                        <td className="px-5 py-3.5 text-gray-900 font-semibold">{tx.customer || t('dashboard.widgets.walk_in_customer')}</td>
                        <td className="px-5 py-3.5 text-gray-600">{tx.restaurant_table || t('dashboard.widgets.counter')}</td>
                        <td className="px-5 py-3.5">
                          <Badge
                            variant="outline"
                            className="border-primary/20 bg-primary/10 text-primary font-semibold"
                          >
                            {orderTypeLabel(tx.order_type || 'Dine In')}
                          </Badge>
                        </td>
                        <td className="px-5 py-3.5 text-gray-500">{tx.posting_date} {tx.posting_time}</td>
                        <td className="px-5 py-3.5">
                          <Badge variant={tx.status === 'Paid' || tx.status === 'Submitted' ? 'success' : 'warning'}>
                            {orderStatusLabel(tx.status)}
                          </Badge>
                        </td>
                        <td className="px-5 py-3.5 text-right font-bold text-gray-900">
                          {formatCurrency(tx.grand_total)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default ReportWidgets;
