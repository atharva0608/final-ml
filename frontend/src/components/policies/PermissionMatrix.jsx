import React from 'react';
import { FiCheck, FiLock, FiAlertCircle } from 'react-icons/fi';

const PermissionMatrix = ({
    allPermissions = [], // List of all available permission objects from API
    selectedSlugs = [],       // Array of strings ['compute:view', ...] currently selected
    inheritedSlugs = [], // Array of permissions inherited from Role (for User view)
    onChange,            // Function(newSlugs)
    readOnly = false
}) => {

    // Ensure allPermissions is an array before reducing
    const safePermissions = Array.isArray(allPermissions) ? allPermissions : [];

    // Group permissions by Module
    const grouped = safePermissions.reduce((acc, perm) => {
        const module = perm.module || 'General';
        if (!acc[module]) acc[module] = [];
        acc[module].push(perm);
        return acc;
    }, {});

    const togglePermission = (slug) => {
        if (readOnly || inheritedSlugs.includes(slug)) return;

        if (selectedSlugs.includes(slug)) {
            onChange(selectedSlugs.filter(s => s !== slug));
        } else {
            onChange([...selectedSlugs, slug]);
        }
    };

    return (
        <div className="space-y-8">
            {Object.entries(grouped).map(([moduleName, perms]) => (
                <div key={moduleName} className="bg-white border rounded-lg overflow-hidden">
                    <div className="bg-gray-50 px-4 py-3 border-b flex justify-between items-center">
                        <h3 className="font-bold text-gray-700">{moduleName}</h3>
                        <span className="text-xs text-gray-500">{perms.length} Permissions</span>
                    </div>

                    <div className="p-4 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                        {perms.map((perm) => {
                            const isInherited = inheritedSlugs.includes(perm.slug);
                            // Safely handle selectedSlugs in case it's null/undefined
                            const safeSelectedSlugs = Array.isArray(selectedSlugs) ? selectedSlugs : [];
                            const isSelected = safeSelectedSlugs.includes(perm.slug) || isInherited;

                            // Risk Color Coding
                            const isHighRisk = perm.slug.includes('delete') || perm.slug.includes('terminate') || perm.slug.includes('bypass');

                            return (
                                <div
                                    key={perm.slug}
                                    onClick={() => togglePermission(perm.slug)}
                                    className={`
                    relative flex items-start p-3 rounded-md border cursor-pointer transition-all
                    ${isSelected ? 'bg-blue-50 border-blue-200' : 'hover:bg-gray-50 border-gray-200'}
                    ${isInherited ? 'opacity-75 cursor-not-allowed bg-gray-100' : ''}
                  `}
                                >
                                    <div className="flex items-center h-5">
                                        <input
                                            type="checkbox"
                                            checked={isSelected}
                                            disabled={isInherited || readOnly}
                                            onChange={() => { }} // Handled by div click
                                            className={`
                        h-4 w-4 rounded text-blue-600 focus:ring-blue-500
                        ${isInherited ? 'text-gray-400' : ''}
                      `}
                                        />
                                    </div>
                                    <div className="ml-3 text-sm">
                                        <label className="font-medium text-gray-900 block">
                                            {perm.name}
                                            {isInherited && <span className="ml-2 text-xs text-gray-500">(Inherited)</span>}
                                        </label>
                                        <p className="text-gray-500 text-xs mt-1">{perm.description}</p>

                                        {/* Security Tags */}
                                        {isHighRisk && (
                                            <span className="inline-flex items-center px-2 py-0.5 mt-2 rounded text-xs font-medium bg-red-100 text-red-800">
                                                <FiAlertCircle className="mr-1" /> High Risk
                                            </span>
                                        )}
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            ))}
        </div>
    );
};

export default PermissionMatrix;
