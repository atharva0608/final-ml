import React from 'react';

const ToggleSwitch = ({ enabled, onChange, label }) => {
  const handleClick = (e) => {
    e.preventDefault();
    e.stopPropagation();
    onChange(!enabled);
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      className={`relative inline-flex items-center h-6 rounded-full w-11 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 ${
        enabled ? 'bg-blue-600' : 'bg-gray-300'
      }`}
    >
      <span className="sr-only">{label}</span>
      <span
        className={`inline-block w-4 h-4 transform bg-white rounded-full transition-transform ${
          enabled ? 'translate-x-6' : 'translate-x-1'
        }`}
      />
    </button>
  );
};

export default ToggleSwitch;
