import React, { useState } from 'react';
import { userAPI } from '../../services/api';
import { Button, Input } from '../shared';
import toast from 'react-hot-toast';

const UserProfile = ({ user }) => {
    const [fullName, setFullName] = useState(user?.full_name || '');
    const [loading, setLoading] = useState(false);

    const updateProfile = async () => {
        setLoading(true);
        try {
            await userAPI.updateProfile({ full_name: fullName });
            toast.success("Profile updated");
            // Optionally refresh user context here if needed
        } catch (error) {
            toast.error("Failed to update profile");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="bg-white p-6 rounded-lg border shadow-sm max-w-xl">
            <h2 className="text-lg font-bold mb-4">User Profile</h2>
            <div className="flex gap-4 items-end">
                <div className="flex-grow">
                    <Input
                        label="Full Name"
                        value={fullName}
                        onChange={e => setFullName(e.target.value)}
                        placeholder="Enter your full name"
                    />
                </div>
                <Button onClick={updateProfile} disabled={loading}>
                    {loading ? 'Saving...' : 'Save'}
                </Button>
            </div>
        </div>
    );
};

export default UserProfile;
