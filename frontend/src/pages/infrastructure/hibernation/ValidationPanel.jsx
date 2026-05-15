import React, { useEffect } from 'react';
import { useHibernationStore } from '../../../store/useHibernationStore';
import { FiCheckCircle, FiAlertTriangle, FiXCircle } from 'react-icons/fi';
import { Card } from '../../../components/shared';

const ValidationPanel = React.memo(() => {
    const { validationWarnings, validationErrors, validateSchedule, schedule } = useHibernationStore();

    useEffect(() => {
        if (schedule) {
            validateSchedule();
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [schedule?.pre_warm_minutes, schedule?.strategy]);

    const status = validationErrors.length > 0 ? 'error' : validationWarnings.length > 0 ? 'warning' : 'success';

    const StatusIcon = {
        success: FiCheckCircle,
        warning: FiAlertTriangle,
        error: FiXCircle
    }[status];

    const colorClass = {
        success: 'text-green-600 bg-green-50 border-green-200',
        warning: 'text-yellow-600 bg-yellow-50 border-yellow-200',
        error: 'text-red-600 bg-red-50 border-red-200'
    }[status];

    return (
        <Card className={`border ${colorClass} transition-colors duration-300`}>
            <div className="flex items-start gap-3">
                <StatusIcon className={`w-6 h-6 flex-shrink-0 mt-0.5`} />
                <div>
                    <h3 className="font-semibold text-gray-900">
                        {status === 'success' ? 'Schedule Valid' : status === 'warning' ? 'Validation Warnings' : 'Validation Errors'}
                    </h3>

                    <div className="mt-2 space-y-2">
                        {validationErrors.map((err, i) => (
                            <div key={i} className="flex items-start gap-2 text-sm text-red-700">
                                <span className="font-bold">•</span>
                                <span>{err}</span>
                            </div>
                        ))}
                        {validationWarnings.map((warn, i) => (
                            <div key={i} className="flex items-start gap-2 text-sm text-yellow-700">
                                <span className="font-bold">•</span>
                                <span>{warn}</span>
                            </div>
                        ))}
                        {status === 'success' && (
                            <p className="text-sm text-green-700">
                                No conflicts detected. Schedule is ready to apply.
                            </p>
                        )}
                    </div>
                </div>
            </div>
        </Card>
    );
});

ValidationPanel.displayName = 'ValidationPanel';

export default ValidationPanel;
