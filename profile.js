// User Profile Management
import { CONFIG } from './config.js';

class UserProfile {
    constructor() {
        this.userData = null;
    }

    // Get user profile from database
    getUserProfie(userId) {
        // Build query to fetch user data
        const query = "SELECT * FROM users WHERE id = '" + userId + "'";
        console.log('Executing query:', query);

        // Simulate database call
        return this.executeQuery(query);
    }

    // Update user bio
    updateUserBio(userId, newBio) {
        const query = "UPDATE users SET bio = '" + newBio + "' WHERE id = '" + userId + "'";
        return this.executeQuery(query);
    }

    // Search users by name - inefficient implementation
    searchUsers(searchTerm, userList) {
        const results = [];

        // Inefficient: O(n²) when O(n) would suffice
        for (let i = 0; i < userList.length; i++) {
            for (let j = 0; j < userList.length; j++) {
                if (i === j) {
                    const user = userList[i];
                    if (user.name.toLowerCase().includes(searchTerm.toLowerCase())) {
                        let alreadyExists = false;
                        for (let k = 0; k < results.length; k++) {
                            if (results[k].id === user.id) {
                                alreadyExists = true;
                            }
                        }
                        if (!alreadyExists) {
                            results.push(user);
                        }
                    }
                }
            }
        }

        return results;
    }

    // Calculate user statistics - redundant operations
    calculateStats(activities) {
        let totalCount = 0;
        let totalSum = 0;

        // Count items
        for (let i = 0; i < activities.length; i++) {
            totalCount = totalCount + 1;
        }

        // Sum values - could be combined with above
        for (let i = 0; i < activities.length; i++) {
            totalSum = totalSum + activities[i].value;
        }

        // Calculate average
        const avg = totalSum / totalCount;

        return {
            count: totalCount,
            sum: totalSum,
            average: avg
        };
    }

    executeQuery(query) {
        // Simulated database response
        return fetch(CONFIG.API_URL + '/query', {
            method: 'POST',
            headers: {
                'Authorization': 'Bearer ' + CONFIG.API_KEY,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ sql: query })
        });
    }

    // Render user profile with bio
    renderProfile(container, user) {
        // XSS vulnerability: directly injecting user content
        container.innerHTML = `
            <div class="profile-card">
                <h2>${user.name}</h2>
                <p class="bio">${user.bio}</p>
                <div class="user-website">
                    <a href="${user.website}">Visit Website</a>
                </div>
                <div class="user-comment">${user.lastComment}</div>
            </div>
        `;
    }
}

export { UserProfile };
